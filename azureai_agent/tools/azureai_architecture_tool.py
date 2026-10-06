import os
import json
import asyncio  # <-- Added for thread isolation
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

from azureai_agent.skillrepo.skill_tools import load_skill, build_skills_prompt

load_dotenv()
max_judge_attempts = 3

class ClarificationQuestions(BaseModel):
    questions: List[str] = Field(
        default=[], 
        description="A list of 1 to 3 direct clarifying questions for the user, or an empty list if none are needed."
    )

def _ask_clarifying_questions(requirements: str, llm: ChatOpenAI) -> str:
    structured_llm = llm.with_structured_output(ClarificationQuestions)
    try:
        result = structured_llm.invoke([HumanMessage(content=check_prompt)])
        questions = result.questions
    except Exception:
        questions = []
        
    refined_context = requirements
    if questions:
        print("\n❓ The AI Architect needs a bit more context to minimize waste:")
        for idx, q in enumerate(questions, 1):
            answer = input(f" [{idx}] {q}\n 👉 Your Answer: ")
            refined_context += f"\n[User Clarification]: Question: {q} | Answer: {answer}"
    return refined_context

def _sync_internal_pipeline(system_request: str) -> str:
    """The actual blocking tool logic, completely wrapped inside a isolated function."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
    agent_tools = [load_skill]
    human_feedback = ""
    
    refined_requirements = _ask_clarifying_questions(system_request, llm)
    
    print("\n🏢 Initializing Architecture Designer Agent...")
    designer_system_prompt = (
        "You are an Elite Azure Solutions Architect. Communicate using accurate service names. "
        "Draft a robust, production-grade text architecture blueprint addressing the user's requirements."
    )
    
    skills_prompt = build_skills_prompt()
    if skills_prompt:
        designer_system_prompt += "\n\n=== AVAILABLE SKILLS METADATA ===\n" + skills_prompt

    designer_agent = create_react_agent(model=llm, tools=agent_tools)
    designer_response = designer_agent.invoke({
        "messages": [
            SystemMessage(content=designer_system_prompt),
            HumanMessage(content=f"Design an architecture for: {refined_requirements}")
        ]
    })
    
    current_layout = str(designer_response["messages"][-1].content)
    
    for attempt in range(1, max_judge_attempts + 1):
        print(f"\n⚖️ [Cost Judge Agent Attempt {attempt}/{max_judge_attempts}] Minimizing architecture costs...")
        judge_system_prompt = (
            "You are a FinOps Cloud Financial Auditor Agent. Modify the layout to minimize running costs "
            "while maintaining operational stability. Recommend Serverless options over dedicated variants."
        )
        if skills_prompt:
            judge_system_prompt += "\n\n=== AVAILABLE SKILLS METADATA ===\n" + skills_prompt
            
        judge_agent = create_react_agent(model=llm, tools=agent_tools)
        
        user_message_content = f"Please critique and minimize the costs for this layout:\n\n{current_layout}"
        if human_feedback:
            user_message_content += f"\n\n⚠️ PREVIOUS REJECTION FEEDBACK FROM HUMAN OPERATOR: {human_feedback}"
            
        judge_response = judge_agent.invoke({
            "messages": [
                SystemMessage(content=judge_system_prompt),
                HumanMessage(content=user_message_content)
            ]
        })
        current_layout = str(judge_response["messages"][-1].content)
    
        print("\n======================= 🔍 FINAL ARCHITECTURE REVIEW =======================")
        print(current_layout)
        print("============================================================================")
        
        approval = input("👉 Do you approve this cost-optimized design layout? (yes/no): ").strip().lower()
        if approval in ["yes", "y"]:
            return current_layout
            
        if attempt < max_judge_attempts:
            human_feedback = input("💡 Provide feedback/changes for the Judge Agent to adjust: ").strip()
        else:
            raise ValueError("Architecture blueprint rejected after max iterations.")


@tool
async def design_and_optimize_architecture(system_request: str) -> str:
    """
    Interactively gathers architectural details, designs a cloud layout based on Azure best practices,
    utilizes a LangGraph agent cost critic to strip out expensive or over-provisioned services, 
    and asks for final human sign-off.
    
    This tool has access to the 'load_skill' tool. If the system request maps to an available skill 
    in your prompt repository, you must call 'load_skill' first to retrieve the precise enterprise 
    architecture requirements before continuing.
    """
    # CRITICAL FIX: Safe execution offloading to a distinct background worker thread pool
    # This prevents the parent orchestrator's state tracker from erroring out during CLI blockages
    return await asyncio.to_thread(_sync_internal_pipeline, system_request)
