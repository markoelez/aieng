"""Todo processing tool."""

import json
from typing import Dict, List

from .base import Tool, ToolResult
from .llm_client import LLMClient
from ..models import Todo, TodoResult
from ..utils import parse_llm_json


class TodoProcessor(Tool):
  """Tool for processing individual todos."""

  def __init__(self, llm_client: LLMClient):
    super().__init__(llm_client.ui_callback)
    self.llm_client = llm_client

  async def execute(
    self, todo: Todo, user_request: str, file_contexts: List[Dict[str, str]], completed_todos: List[Todo] = None
  ) -> ToolResult:
    """Process a single todo with chain-of-thought reasoning."""
    if completed_todos is None:
      completed_todos = []

    try:
      prompt = self._build_todo_prompt(todo, user_request, file_contexts, completed_todos)

      messages = [
        {
          "role": "system",
          "content": "You are an expert software engineer who completes tasks efficiently by generating file edits. You are decisive, productive, and focus on delivering working code rather than excessive analysis.",
        },
        {"role": "user", "content": prompt},
      ]

      result = await self.llm_client.execute(messages, response_format={"type": "json_object"})

      if not result.success:
        return ToolResult(success=False, error=result.error)

      try:
        parsed = parse_llm_json(result.data)
        cleaned_data = self._clean_todo_result(parsed)
        todo_result = TodoResult(**cleaned_data)
        return ToolResult(success=True, data=todo_result)

      except (json.JSONDecodeError, Exception) as e:
        return ToolResult(
          success=True,
          data=TodoResult(thinking=f"JSON decode error: {e}", edits=[], completed=False, next_steps="Fix JSON formatting and retry"),
        )

    except Exception as e:
      return ToolResult(
        success=True,
        data=TodoResult(
          thinking=f"Error processing todo: {e}", edits=[], completed=False, next_steps="Retry or break down into smaller tasks"
        ),
      )

  def _build_todo_prompt(self, todo: Todo, user_request: str, file_contexts: List[Dict[str, str]], completed_todos: List[Todo]) -> str:
    """Build the prompt for todo processing."""
    completed_context = ""
    if completed_todos:
      completed_context = "Previously completed todos:\n" + "\n".join([f"- {t.task}" for t in completed_todos]) + "\n\n"

    context_info = "\n".join(
      [
        f"--- {ctx['path']} ---\n{ctx['content'][:1000]}..." if len(ctx["content"]) > 1000 else f"--- {ctx['path']} ---\n{ctx['content']}"
        for ctx in file_contexts
      ]
    )

    return f"""
You are an AI coding assistant working on this specific todo item.

Original user request: {user_request}
Current todo: {todo.task}
Reasoning: {todo.reasoning}

{completed_context}File contexts:
{context_info}

INSTRUCTIONS:
1. Think step-by-step about how to complete this specific todo
2. Use the provided file contexts to understand the codebase
3. Generate the necessary file edits to complete this todo immediately
4. Mark the todo as completed if you have generated all necessary edits

CRITICAL RULES:
- AVOID running commands unless absolutely necessary (like creating directories)
- AVOID searches unless the exact information you need is missing from file contexts
- FOCUS on generating file edits to complete the task
- If a todo asks to "add tests", "create files", or "modify code", generate the actual edits immediately
- Don't over-analyze - if you have enough context, make the edits

Respond with JSON containing:
- "thinking": Your step-by-step reasoning about how to complete this todo
- "searches": List of search operations (USE SPARINGLY - only if critical info missing from contexts)
- "commands": List of terminal commands (USE SPARINGLY - only for mkdir, etc.)
- "edits": List of file edits needed - THIS IS THE MAIN FOCUS, GENERATE THESE TO COMPLETE THE TODO
- "completed": true if this todo is fully completed with edits, false only if you genuinely cannot proceed
- "next_steps": What should happen next (only if completed=false)

For edits (THE PRIMARY OUTPUT), each edit must have these fields:
- "file_path": Path to the file (can be new or existing)
- "old_content": Use "REWRITE_ENTIRE_FILE" for existing files, "" for new files
- "new_content": The complete new content of the file
- "description": Brief description of what this edit does

PRODUCTIVITY TIPS:
- The file contexts provide sufficient information for most tasks
- Generate edits immediately rather than searching for more information
- Focus on completing the todo with concrete file changes
- Avoid unnecessary exploration - be decisive and productive
"""

  def _clean_todo_result(self, parsed: Dict) -> Dict:
    """Clean and validate the parsed todo result."""
    cleaned = {
      "thinking": str(parsed.get("thinking", "")),
      "commands": self._clean_commands(parsed.get("commands", [])),
      "searches": self._clean_searches(parsed.get("searches", [])),
      "edits": self._clean_edits(parsed.get("edits", [])),
      "completed": bool(parsed.get("completed", False)),
      "next_steps": self._clean_next_steps(parsed.get("next_steps", "")),
    }
    return cleaned

  def _clean_commands(self, commands) -> List[Dict]:
    """Clean and validate commands."""
    if not isinstance(commands, list):
      return []

    clean_commands = []
    for cmd in commands:
      if isinstance(cmd, dict):
        clean_commands.append({"command": str(cmd.get("command", "")), "description": str(cmd.get("description", ""))})
      elif isinstance(cmd, str):
        clean_commands.append({"command": cmd, "description": "Command execution"})
    return clean_commands

  def _clean_searches(self, searches) -> List[Dict]:
    """Clean and validate searches."""
    if not isinstance(searches, list):
      return []

    clean_searches = []
    for search in searches:
      if isinstance(search, dict):
        clean_searches.append(
          {
            "query": str(search.get("query", "")),
            "command": str(search.get("command", "")),
            "description": str(search.get("description", "")),
          }
        )
    return clean_searches

  def _clean_edits(self, edits) -> List[Dict]:
    """Clean and validate edits."""
    if not isinstance(edits, list):
      return []

    clean_edits = []
    for edit in edits:
      if isinstance(edit, dict):
        clean_edits.append(
          {
            "file_path": str(edit.get("file_path", "")),
            "old_content": str(edit.get("old_content", "")),
            "new_content": str(edit.get("new_content", "")),
            "description": str(edit.get("description", "")),
          }
        )
    return clean_edits

  def _clean_next_steps(self, next_steps) -> str:
    """Clean and validate next_steps."""
    if isinstance(next_steps, list):
      if next_steps:
        return " ".join(str(item) for item in next_steps)
      else:
        return ""
    elif isinstance(next_steps, str):
      return next_steps
    else:
      return str(next_steps) if next_steps else ""
