from langchain.agents import create_agent


from azureai_agent.llm.factory import get_llm
from azureai_agent.agent.tools import search_codebase
from azureai_agent.observability.logger import get_logger
from azureai_agent.skillrepo.skill_tools import load_skill, build_skills_prompt
from azureai_agent.mcp.azureaiagent_mcp_client import get_azureaiagent_mcp_tools

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are an AI agent that can perform various tasks using the skills available in the skill repository. You have access to a set of tools that allow you to load and utilize these skills as needed.
"""


async def build_agent(checkpointer):
  """Create and return a LangChain agent ith persistent memory."""
  llm = get_llm()
  mcp_tools = await get_azureaiagent_mcp_tools()
  skills_prompt = build_skills_prompt()
  full_prompt = SYSTEM_PROMPT
  if skills_prompt:
      full_prompt = SYSTEM_PROMPT + "\n\n" + skills_prompt

  tools = [
      load_skill,
      *mcp_tools
  ]


  return create_agent(
      llm,
      tools=tools,
      system_prompt=full_prompt,
      checkpointer=checkpointer,
  )