import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt


# Load .env before anything else
load_dotenv(Path(__file__).parent.parent / ".env")


console = Console()
logger = get_logger(__name__)


def run():
   logger.info("Starting azure ai agent")
   console.print("\n[bold blue]Azure Ai Agent[/bold blue] — RAG-powered azure architect assistant")



if __name__ == "__main__":
   run()
