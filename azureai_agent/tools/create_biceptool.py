import asyncio
import os
import re
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.tools import tool

load_dotenv()

def _clean_code(raw_text: str) -> str:
    """Removes markdown code blocks if the LLM includes them."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```bicep\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()

async def _prompt_human(stage_message: str, code_to_show: str = "") -> bool:
    """Helper function to show code context and handle human terminal blocking gates asynchronously."""
    print("\n======================= 🔍 HUMAN REVIEW GATE =======================")
    print(f"👉 STAGE: {stage_message}")
    if code_to_show:
        print("-------------------- CURRENT BICEP CODE --------------------")
        print(code_to_show)
        print("------------------------------------------------------------")
    
    # Run blocking input() in a separate thread so it doesn't block the async event loop
    user_input = await asyncio.to_thread(input, "Proceed? (yes/no): ")
    user_approval = user_input.strip().lower()
    print("====================================================================")
    return user_approval in ["yes", "y"]

@tool
async def generate_and_validate_bicep_with_strict_hitl(architecture_requirements: str, output_path: str = "main.bicep") -> str:
    """
    Generates Azure Bicep code based on requirements, prompts for human approval before 
    running the MCP server compiler, and prompts again after each validation failure 
    before triggering the self-healing repair cycle.
    
    Args:
        architecture_requirements: Detailed description of the Azure system architecture to build.
        output_path: The local file path where the valid .bicep file should be saved.
        
    Returns:
        A JSON string containing the success status, file path, and diagnostic execution traces.
    """
    # Directly await the async execution function instead of asyncio.run()
    return await _execute_strict_hitl_pipeline(architecture_requirements, output_path)
async def _execute_strict_hitl_pipeline(requirements: str, output_path: str) -> str:
    max_retries = 3
    abs_path = os.path.abspath(output_path)
    openai_client = OpenAI()
    
    system_instructions = (
        "You are a specialized Cloud Infrastructure Engineer. Output ONLY clean, valid Azure Bicep code "
        "based on the user's requirements. Do not wrap code blocks in backticks like ```bicep or ```. "
        "Provide no explanations, no text commentary, and no markdown wrapper formatting.\n\n"
        "CRITICAL DEFAULT CONSTANTS:\n"
        "- Always include a default parameter or variable for region named 'location' set to 'eastus' (e.g., param location string = 'eastus').\n"
        "- Always include a default configuration variable or parameter for the environment name set to 'dev' (e.g., param envName string = 'dev').\n\n"
        "STRICT BUDGET & COST OPTIMIZATION GUIDELINES:\n"
        "- You must prioritize the lowest possible running cost for all services.\n"
        "- Compute: Use Serverless, Dev/Test, or Free SKUs (e.g., App Service Plan B1/F1, Azure Functions Serverless).\n"
        "- Storage: Use Standard LRS (Locally Redundant Storage) and strip geo-replication options.\n"
        "- Databases: Always select Serverless tiers with auto-pause enabled (e.g., Azure SQL Serverless, Cosmos DB Serverless).\n"
        "- Networking: Avoid expensive persistent items like application gateways or Azure Firewalls unless explicitly requested; favor basic VNet peerings and network security groups (NSGs)."
    )

    # Isolated message history strictly for the inner OpenAI generation/healing pipeline
    repair_history = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": f"Generate a Bicep template for: {requirements}"}
    ]

    # --- 1. INITIAL GENERATION ---
    print("\n🤖 Tool Brain: Generating initial draft layout...")
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=repair_history,
        temperature=0.1
    )
    bicep_code = _clean_code(response.choices[0].message.content)

    # --- GATE 1: Before executing MCP Server for the first time ---
    approved = await _prompt_human("Initial generation complete. Approve code to run the initial MCP server verification check?", bicep_code)
    if not approved:
        print("🛑 Workflow aborted by human operator before initial MCP compilation.")
        return f'{{"success": false, "error": "Human rejected the initial draft layout."}}'

    # --- 2. START MCP SERVER PROCESS ---
    server_params = StdioServerParameters(
        command="dnx",
        args=["-y", "Azure.Bicep.McpServer"],
        env=dict(os.environ)
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            tools_response = await session.list_tools()
            tool_names = [t.name for t in tools_response.tools]
            validation_tool = next((t for t in ["build_bicep", "validate_bicep", "get_diagnostics"] if t in tool_names), None)
            
            if not validation_tool:
                return f'{{"success": false, "error": "Validation tool missing from MCP server."}}'

            # --- 3. EVALUATION & LOOPING HEALING GATES ---
            for attempt in range(1, max_retries + 1):
                print(f"\n💾 [Attempt {attempt}/{max_retries}] Saving template changes to file...")
                with open(abs_path, "w") as f:
                    f.write(bicep_code)

                print(f"🔬 Compiling file via MCP Server using tool '{validation_tool}'...")
                tool_result = await session.call_tool(
                    name=validation_tool,
                    arguments={"filePath": abs_path}
                )
                
                diagnostics_output = "".join([c.text for c in tool_result.content if hasattr(c, 'text')])
                
                # Verify if compilation errors exist
                if "error BCP" in diagnostics_output or ("BCP" in diagnostics_output and "failed" in diagnostics_output.lower()):
                    print(f"❌ Validation FAILED on attempt {attempt}.")
                    print(f"--- MCP Error Stack Summary ---\n{diagnostics_output}\n-------------------------------")
                    
                    if attempt == max_retries:
                        return f'{{"success": false, "attempts": {attempt}, "file_path": "{abs_path}", "errors": "Reached maximum healing retries."}}'
                    
                    # --- GATE 2+: Prompt after every validation failure before running self-healing ---
                    gate_msg = f"Validation attempt {attempt} failed. Approve triggering the LLM self-healing repair cycle?"
                    if not await _prompt_human(gate_msg):
                        print("🛑 Workflow aborted by human operator after validation failure.")
                        return f'{{"success": false, "attempts": {attempt}, "file_path": "{abs_path}", "error": "Human aborted healing after validation errors occurred."}}'
                    
                    print("🩹 Healing approved. Packaging error logs back to OpenAI...")
                    
                    # Construct clean, isolated text messages for the repair request
                    repair_messages = [
                        {"role": "system", "content": system_instructions},
                        {"role": "user", "content": f"Generate a Bicep template for: {requirements}"},
                        {"role": "assistant", "content": bicep_code},
                        {
                            "role": "user",
                            "content": (
                                f"The Bicep MCP server validation failed with the following compilation errors:\n\n{diagnostics_output}\n\n"
                                "Please analyze these specific BCP error codes, repair the syntax or parameter structure errors in the file, "
                                "and output the full, corrected Bicep template."
                            )
                        }
                    ]

                    repair_response = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=repair_messages,
                        temperature=0.1
                    )
                    bicep_code = _clean_code(repair_response.choices[0].message.content)
                else:
                    print(f"🎉 SUCCESS! The infrastructure template passed verification on attempt {attempt}.")
                    return f'{{"success": true, "attempts": {attempt}, "file_path": "{abs_path}"}}'