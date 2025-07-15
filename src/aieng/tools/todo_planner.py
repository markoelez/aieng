"""Todo planning tool."""

import json
from typing import Dict, List

from .base import Tool, ToolResult
from .llm_client import LLMClient
from ..models import TodoPlan, Todo


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
Break down this request into 1-3 concise action items.

Request: {user_request}

Files: {context_summary}

Create JSON with:
- "summary": Brief plan overview (max 10 words)
- "todos": List with:
  - "id": Number (1, 2, 3...)
  - "task": Short, direct action (max 8 words, e.g. "Add tests", "Update README", "Fix login bug")
  - "reasoning": Brief why (max 6 words)
  - "priority": "high", "medium", or "low" 
  - "dependencies": Array of prerequisite todo IDs

Keep todos:
- Ultra-concise and actionable
- Focus on specific deliverables
- Avoid verbose descriptions

Example bad: "Create comprehensive unit tests for user authentication functions with proper mocking"
Example good: "Add user auth tests"
"""
            
            messages = [
                {"role": "system", "content": "You create concise, targeted action plans. Avoid verbose explanations."},
                {"role": "user", "content": planning_prompt},
            ]
            
            result = await self.llm_client.execute(messages, response_format={"type": "json_object"})
            
            if not result.success:
                return self._create_fallback_plan(user_request)
            
            try:
                parsed = json.loads(result.data)
                todo_plan = TodoPlan(**parsed)
                return ToolResult(success=True, data=todo_plan)
            except (json.JSONDecodeError, Exception):
                return self._create_fallback_plan(user_request)
                
        except Exception as e:
            return self._create_fallback_plan(user_request, str(e))
    
    def _create_fallback_plan(self, user_request: str, error: str = None) -> ToolResult:
        """Create a fallback todo plan."""
        plan = TodoPlan(
            summary=f"Simple plan for: {user_request}",
            todos=[Todo(
                id=1, 
                task=user_request, 
                reasoning="Direct implementation of user request", 
                priority="high", 
                dependencies=[]
            )],
        )
        return ToolResult(success=True, data=plan)