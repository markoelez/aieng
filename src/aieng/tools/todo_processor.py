"""Todo processing tool."""

import json
from typing import Dict, List, Optional

from .base import Tool, ToolResult
from ..utils import parse_llm_json
from ..models import Todo, TodoResult
from .llm_client import LLMClient


class TodoProcessor(Tool):
  """Tool for processing individual todos."""

  def __init__(self, llm_client: LLMClient):
    super().__init__(llm_client.ui_callback)
    self.llm_client = llm_client

  async def execute(
    self,
    todo: Todo,
    user_request: str,
    file_contexts: List[Dict[str, str]],
    completed_todos: Optional[List[Todo]] = None,
  ) -> ToolResult:
    """Process a single todo with chain-of-thought reasoning."""
    if completed_todos is None:
      completed_todos = []

    try:
      prompt = self._build_todo_prompt(todo, user_request, file_contexts, completed_todos)

      messages = [
        {
          "role": "system",
          "content": "You are an expert software engineer who completes tasks efficiently by generating file edits. You are decisive, productive, and focus on delivering working code rather than excessive analysis. You MUST respond ONLY with valid JSON. Do not include any text before or after the JSON.",
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
    return {
      "thinking": str(parsed.get("thinking", "")),
      "commands": self._clean_dict_list(parsed.get("commands", []), ["command", "description"]),
      "searches": self._clean_dict_list(parsed.get("searches", []), ["query", "command", "description"]),
      "edits": self._clean_dict_list(parsed.get("edits", []), ["file_path", "old_content", "new_content", "description"]),
      "completed": bool(parsed.get("completed", False)),
      "next_steps": self._clean_next_steps(parsed.get("next_steps", "")),
    }

  def _clean_dict_list(self, items, keys: List[str]) -> List[Dict]:
    """Clean and validate a list of dictionaries with specified keys."""
    if not isinstance(items, list):
      return []
    return [{key: str(item.get(key, "")) for key in keys} for item in items if isinstance(item, dict)]

  def _clean_next_steps(self, next_steps) -> str:
    """Clean and validate next_steps."""
    if isinstance(next_steps, list):
      return " ".join(str(item) for item in next_steps) if next_steps else ""
    if isinstance(next_steps, str):
      return next_steps
    return str(next_steps) if next_steps else ""
