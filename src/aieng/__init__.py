import asyncio
from typing import List, Optional

import click

from .orchestrator import AIAgentOrchestrator


@click.command()
@click.option("--model", default="grok-4", help="OpenAI model to use (default: grok-4)")
@click.option("--project-root", default=".", help="Project root directory (default: current directory)")
@click.option("--request", help="Single request to process (non-interactive mode)")
@click.option("--files", help="Comma-separated list of specific files to include in context")
@click.option("--interactive/--no-interactive", default=True, help="Run in interactive mode")
def main(model: str, project_root: str, request: Optional[str], files: Optional[str], interactive: bool):
  """
  AI Coding Agent - A terminal-based AI assistant for code changes.

  This tool helps you make code changes by analyzing your requests,
  gathering relevant file context, and generating structured diffs
  that you can review and approve.
  """

  file_list: List[str] = []
  if files:
    file_list = [f.strip() for f in files.split(",")]

  orchestrator = AIAgentOrchestrator(model=model, project_root=project_root)

  if request and not interactive:
    # Single request mode
    async def run_single():
      success = await orchestrator.run_single_request(request, file_list)
      return 0 if success else 1

    exit_code = asyncio.run(run_single())
    exit(exit_code)

  elif request and interactive:
    # Start with a request, then go interactive
    async def run_with_initial_request():
      await orchestrator.process_user_request(request, file_list)
      await orchestrator.run_interactive_session()

    asyncio.run(run_with_initial_request())

  else:
    # Full interactive mode
    asyncio.run(orchestrator.run_interactive_session())
