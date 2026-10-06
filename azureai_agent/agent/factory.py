from azureai_agent.tools.azureai_architecture_tool import design_and_optimize_architecture
from azureai_agent.tools.create_biceptool import generate_and_validate_bicep_with_strict_hitl
from langchain.agents import create_agent


from azureai_agent.llm.factory import get_llm
from azureai_agent.observability.logger import get_logger

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are an AI agent that can perform various tasks using the skills available in the skill repository. You have access to a set of tools that allow you to load and utilize these skills as needed.
"""


async def build_agent(checkpointer):
  """Create and return a LangChain agent ith persistent memory."""
  llm = get_llm()

  tools = [
      design_and_optimize_architecture,
      generate_and_validate_bicep_with_strict_hitl
  ]


  return create_agent(
      llm,
      tools=tools,
      system_prompt=SYSTEM_PROMPT,
      checkpointer=checkpointer,
  )