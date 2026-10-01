from langchain.agents import create_agent


from azureai_agent.llm.factory import get_llm
from azureai_agent.agent.tools import search_codebase
from azureai_agent.observability.logger import get_logger
from azureai_agent.skillrepo.skill_tools import load_skill, build_skills_prompt


logger = get_logger(__name__)


SYSTEM_PROMPT = """You are an expert Cloud & AI Solutions Architect specializing in the Microsoft Azure ecosystem. Your mission is to design enterprise-grade, production-ready system architectures that are highly scalable, highly available, secure, and rigorously cost-optimized.

When presented with a business problem, application requirements, or an engineering challenge, structure your response using the following architectural pillars:

"""


async def build_agent(checkpointer):
  """Create and return a LangChain agent ith persistent memory."""
  llm = get_llm()

  skills_prompt = build_skills_prompt()
  full_prompt = SYSTEM_PROMPT
  if skills_prompt:
      full_prompt = SYSTEM_PROMPT + "\n\n" + skills_prompt

  tools = [
      load_skill,
  ]


  return create_agent(
      llm,
      tools=tools,
      system_prompt=full_prompt,
      checkpointer=checkpointer,
  )