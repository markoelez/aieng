"""Todo planning tool."""

import json
from typing import Dict, List

from .base import Tool, ToolResult
from ..models import Todo, TodoPlan
from ..utils import parse_llm_json
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
You are an engineering manager creating a strategic implementation plan. Break down this user request into 2-5 high-level objectives that an engineer can execute.

User Request: {user_request}

Available Codebase:
{context_summary}

Your role: Create strategic, actionable objectives that give the engineer flexibility in implementation approach.

PLANNING PRINCIPLES:
1. Focus on OUTCOMES and OBJECTIVES, not specific implementation details
2. Give the engineer room to decide HOW to implement
3. Tasks should be measurable and testable when complete
4. Think at the feature/capability level, not file level
5. Order tasks by logical dependencies and priority

Examples of GOOD manager-level tasks:

Request: "add tests"
Bad: "Create tests/test_agent.py for Agent class methods"
Good: "Establish comprehensive unit test coverage", "Implement integration testing strategy"

Request: "improve error handling"
Bad: "Add try-catch blocks to LLM calls in agent.py" 
Good: "Enhance error handling and recovery mechanisms", "Implement user-friendly error reporting"

Request: "add documentation"
Bad: "Add docstrings to Agent class methods"
Good: "Create comprehensive user documentation", "Document API and architecture"

Request: "optimize performance"
Bad: "Optimize LLM calls in agent.py"
Good: "Improve system performance and response times", "Optimize resource usage patterns"

Return JSON with:
{{
  "summary": "Strategic plan overview (max 15 words)",
  "todos": [
    {{
      "id": 1,
      "task": "High-level objective/capability to implement (max 15 words)",
      "reasoning": "Business value or technical need (max 12 words)", 
      "priority": "high/medium/low",
      "dependencies": []
    }}
  ]
}}

FOCUS: Strategic objectives, not implementation details. Let the engineer decide the HOW.
"""

      messages = [
        {
          "role": "system",
          "content": "You are an experienced engineering manager who creates strategic implementation plans. Focus on high-level objectives and outcomes, giving engineers flexibility in how they implement solutions.",
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
