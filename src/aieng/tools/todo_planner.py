"""Todo planning tool."""

import json
from typing import Dict, List

from .base import Tool, ToolResult
from ..utils import parse_llm_json
from ..models import Todo, TodoPlan
from .llm_client import LLMClient


class TodoPlanner(Tool):
  """Tool for generating todo plans."""

  def __init__(self, llm_client: LLMClient):
    super().__init__(llm_client.ui_callback)
    self.llm_client = llm_client

  async def execute(self, user_request: str, file_contexts: List[Dict[str, str]]) -> ToolResult:
    """Generate a todo plan for the user request."""
    try:
      context_summary = "\n".join([f"- {ctx['path']}: {len(ctx['content'])} chars" for ctx in file_contexts])

      planning_prompt = f"""
You are a senior engineer breaking down a user request into concrete, actionable tasks. Create 2-5 focused tasks that can be implemented one by one.

User Request: {user_request}

Available Codebase:
{context_summary}

Your goal: Break down the request into distinct implementation tasks that are:
- Concrete enough to start working on immediately
- Focused on a specific aspect or component
- Not prescriptive about exact implementation details
- Ordered logically with clear dependencies

TASK GUIDELINES:
1. Each task should focus on implementing one specific capability or component
2. Tasks should be completable in a reasonable time (not too broad)
3. Avoid being too prescriptive about specific files or implementation details
4. Make tasks concrete and actionable, not vague objectives
5. Order tasks so each builds on the previous

GOOD EXAMPLES:

Request: "add tests to this project"
Too vague: "Establish comprehensive testing infrastructure"
Too specific: "Create test_agent.py with test_process_request method"
Just right: "Create unit tests for agent functionality", "Add tests for orchestrator workflows"

Request: "improve error handling"
Too vague: "Enhance error handling mechanisms"
Too specific: "Add try-catch to line 45 in agent.py"
Just right: "Add error handling to LLM API calls", "Implement user-friendly error messages"

Request: "add documentation"
Too vague: "Create comprehensive documentation"
Too specific: "Add docstring to Agent.__init__ method"
Just right: "Write user guide with examples", "Document main classes and methods"

Return JSON with:
{{
  "summary": "Clear plan description (max 15 words)",
  "todos": [
    {{
      "id": 1,
      "task": "Concrete, focused task to implement (max 12 words)",
      "reasoning": "Why this task is needed (max 10 words)", 
      "priority": "high/medium/low",
      "dependencies": []
    }}
  ]
}}

REMEMBER: Create tasks that are concrete actions, not broad objectives or tiny details.
"""

      messages = [
        {
          "role": "system",
          "content": "You are a senior engineer who breaks down requests into concrete, focused implementation tasks. Create actionable tasks that are specific enough to work on but not prescriptive about implementation details.",
        },
        {"role": "user", "content": planning_prompt},
      ]

      result = await self.llm_client.execute(messages, response_format={"type": "json_object"})

      if not result.success:
        return self._create_fallback_plan(user_request, f"LLM call failed: {result.error}")

      try:
        parsed = parse_llm_json(result.data)

        # Validate that we have proper structure
        if "todos" not in parsed or not parsed["todos"]:
          return self._create_fallback_plan(user_request, "No todos in LLM response")

        # Ensure todos have proper structure and aren't just repeating the request
        for i, todo in enumerate(parsed["todos"]):
          task = todo.get("task", "").strip().lower()
          request_lower = user_request.strip().lower()

          # Check if the LLM is just repeating the user request or being too vague
          if not task or task == request_lower or len(task.split()) <= 2:  # Very short, likely vague
            return self._create_fallback_plan(user_request, f"LLM task too vague: '{todo.get('task', '')}'")

        # Check if we have enough strategic todos
        if len(parsed["todos"]) < 2:
          return self._create_fallback_plan(user_request, "Need more strategic task breakdown")

        todo_plan = TodoPlan(**parsed)
        return ToolResult(success=True, data=todo_plan)

      except json.JSONDecodeError as e:
        return self._create_fallback_plan(user_request, f"JSON decode error: {e}")
      except Exception as e:
        return self._create_fallback_plan(user_request, f"Validation error: {e}")

    except Exception as e:
      return self._create_fallback_plan(user_request, str(e))

  def _create_fallback_plan(self, user_request: str, error: str = None) -> ToolResult:
    """Create a simple fallback when LLM completely fails."""
    # Only use this as a last resort - single todo that forces the user to be more specific
    todos = [
      Todo(
        id=1,
        task=f"Please be more specific: {user_request[:40]}...",
        reasoning="Need clearer requirements",
        priority="high",
        dependencies=[],
      )
    ]
    summary = "Request needs clarification"

    plan = TodoPlan(summary=summary, todos=todos)
    return ToolResult(success=True, data=plan)
