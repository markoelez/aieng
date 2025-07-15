import asyncio

import click

from .orchestrator import AIAgentOrchestrator


@click.command()
@click.option("--project-root", default=".", help="Project root directory (default: current directory)")
def main(project_root: str):
  """
  AI Coding Agent - A terminal-based AI assistant for code changes.

  This tool helps you make code changes by analyzing your requests,
  gathering relevant file context, and generating structured diffs
  that you can review and approve.
  """
  orchestrator = AIAgentOrchestrator(model="grok-4", project_root=project_root)
  asyncio.run(orchestrator.run_interactive_session())
