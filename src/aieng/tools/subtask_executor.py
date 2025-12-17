"""Subtask execution tool for progressive todo completion."""

from typing import Dict, List, Optional

from .base import Tool, ToolResult
from ..utils import parse_llm_json
from ..models import Todo
from .llm_client import LLMClient


class SubtaskExecutor(Tool):
  """Tool for breaking down and executing todo subtasks progressively."""

  def __init__(self, llm_client: LLMClient):
    super().__init__(llm_client.ui_callback)
    self.llm_client = llm_client

  async def execute(self, **kwargs) -> ToolResult:
    """Execute the tool - not used directly, see plan_subtasks and execute_subtask."""
    return ToolResult(
      success=False, error="SubtaskExecutor should not be called directly. Use plan_subtasks() or execute_subtask() instead."
    )

  async def plan_subtasks(self, todo: Todo, user_request: str, file_contexts: List[Dict[str, str]]) -> ToolResult:
    """Break down a todo into subtasks."""
    try:
      prompt = self._build_planning_prompt(todo, user_request, file_contexts)

      messages = [
        {
          "role": "system",
          "content": "You are an expert at breaking down coding tasks into small, sequential subtasks. Each subtask should be a single file operation. You MUST respond ONLY with valid JSON.",
        },
        {"role": "user", "content": prompt},
      ]

      result = await self.llm_client.execute(messages, response_format={"type": "json_object"})

      if not result.success:
        return ToolResult(success=False, error=result.error)

      try:
        parsed = parse_llm_json(result.data)
        subtasks = parsed.get("subtasks", [])
        return ToolResult(success=True, data=subtasks)

      except Exception as e:
        return ToolResult(success=False, error=f"Failed to parse subtasks: {e}")

    except Exception as e:
      return ToolResult(success=False, error=str(e))

  async def execute_subtask(
    self,
    subtask: Dict[str, str],
    todo: Todo,
    user_request: str,
    file_contexts: List[Dict[str, str]],
    completed_subtasks: Optional[List[Dict[str, str]]] = None,
  ) -> ToolResult:
    """Execute a single subtask."""
    if completed_subtasks is None:
      completed_subtasks = []

    try:
      prompt = self._build_execution_prompt(subtask, todo, user_request, file_contexts, completed_subtasks)

      messages = [
        {
          "role": "system",
          "content": "You are generating code for a single file operation. Focus on this specific subtask only. You MUST respond ONLY with valid JSON containing the file edit.",
        },
        {"role": "user", "content": prompt},
      ]

      result = await self.llm_client.execute(messages, response_format={"type": "json_object"})

      if not result.success:
        return ToolResult(success=False, error=result.error)

      try:
        parsed = parse_llm_json(result.data)
        edit = self._clean_edit_data(parsed)
        return ToolResult(success=True, data=edit)

      except Exception as e:
        return ToolResult(success=False, error=f"Failed to parse edit: {e}")

    except Exception as e:
      return ToolResult(success=False, error=str(e))

  def _build_planning_prompt(self, todo: Todo, user_request: str, file_contexts: List[Dict[str, str]]) -> str:
    """Build prompt for subtask planning."""
    context_info = "\n".join([f"- {ctx['path']}" for ctx in file_contexts])

    return f"""Break down this todo into specific subtasks that should be executed sequentially.

Original request: {user_request}
Todo: {todo.task}
Reasoning: {todo.reasoning}

Available files:
{context_info}

Break this down into subtasks where each subtask is a single file operation (create, modify, or delete).
Order them logically so dependencies are handled first.

Respond with JSON containing:
- "subtasks": Array of subtask objects, each with:
  - "description": What this subtask does (e.g., "Create main.py with hello function")
  - "file_path": The file this subtask will affect
  - "operation": "create", "modify", or "delete"
  - "order": Sequential order number (1, 2, 3, etc.)

Example response:
{{
  "subtasks": [
    {{
      "description": "Create tests directory",
      "file_path": "tests/",
      "operation": "create",
      "order": 1
    }},
    {{
      "description": "Add __init__.py to tests directory",
      "file_path": "tests/__init__.py",
      "operation": "create",
      "order": 2
    }}
  ]
}}"""

  def _build_execution_prompt(
    self,
    subtask: Dict[str, str],
    todo: Todo,
    user_request: str,
    file_contexts: List[Dict[str, str]],
    completed_subtasks: List[Dict[str, str]],
  ) -> str:
    """Build prompt for subtask execution."""

    # Find relevant context for this file
    relevant_context = None
    for ctx in file_contexts:
      if ctx["path"] == subtask["file_path"]:
        relevant_context = ctx["content"]
        break

    completed_info = ""
    if completed_subtasks:
      completed_info = "\nCompleted subtasks:\n"
      for st in completed_subtasks:
        completed_info += f"- {st['description']}\n"

    return f"""Execute this specific subtask.

Original request: {user_request}
Current todo: {todo.task}

Current subtask: {subtask["description"]}
File: {subtask["file_path"]}
Operation: {subtask["operation"]}

{completed_info}

Current file content:
{relevant_context if relevant_context else "FILE DOES NOT EXIST"}

Generate a JSON response with:
- "file_path": The path to this file
- "old_content": Use "REWRITE_ENTIRE_FILE" for existing files, "" for new files
- "new_content": The complete content for this file
- "description": What this edit accomplishes

Focus on this specific subtask only."""

  def _clean_edit_data(self, parsed: Dict) -> Dict[str, str]:
    """Clean and validate the edit data."""
    return {
      "file_path": parsed.get("file_path", ""),
      "old_content": parsed.get("old_content", ""),
      "new_content": parsed.get("new_content", ""),
      "description": parsed.get("description", ""),
    }
