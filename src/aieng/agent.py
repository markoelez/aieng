"""AI Agent for code generation and modification."""

import os
from typing import TYPE_CHECKING, Any, Dict, List, Callable, Optional

from .tools import (
  LLMClient,
  TodoPlanner,
  TodoProcessor,
  EditSummarizer,
  CommandExecutor,
  SubtaskExecutor,
)
from .utils import parse_llm_json
from .config import DEFAULT_MODEL
from .models import (
  Todo,
  FileEdit,
  TodoPlan,
  TodoResult,
  LLMResponse,
  CommandResult,
  SelfReflection,
)

if TYPE_CHECKING:
  from .todo_manager import TodoManager


class Agent:
  """Main agent class that coordinates various tools."""

  def __init__(
    self,
    model: str = DEFAULT_MODEL,
    ui_callback: Optional[Callable[..., None]] = None,
    project_root: str = ".",
    config: Optional[Dict[str, Any]] = None,
  ):
    """Initialize the agent with its tools."""
    self.project_root = os.path.abspath(project_root)
    self.ui_callback = ui_callback
    self._todo_manager: Optional["TodoManager"] = None

    # Initialize tools
    self.llm_client = LLMClient(model=model, config=config, ui_callback=ui_callback)
    self.command_executor = CommandExecutor(project_root=project_root, ui_callback=ui_callback)
    self.todo_planner = TodoPlanner(self.llm_client)
    self.todo_processor = TodoProcessor(self.llm_client)
    self.edit_summarizer = EditSummarizer(self.llm_client)
    self.subtask_executor = SubtaskExecutor(self.llm_client)

  def set_todo_manager(self, todo_manager: "TodoManager") -> None:
    """Set the TodoManager reference for dynamic todo modification.

    Args:
      todo_manager: The TodoManager instance to use
    """
    self._todo_manager = todo_manager

  def add_todo(
    self, task: str, reasoning: str = "", priority: str = "medium", active_form: str = "", dependencies: Optional[List[int]] = None
  ) -> Optional[Todo]:
    """Dynamically add a new todo during execution.

    This allows the agent to add new todos as it discovers more work is needed.

    Args:
      task: The task description
      reasoning: Why this task is needed
      priority: Task priority (high/medium/low)
      active_form: Present continuous form for UI display
      dependencies: List of todo IDs this depends on

    Returns:
      The newly created Todo, or None if no TodoManager is set
    """
    if self._todo_manager is None:
      return None
    return self._todo_manager.add_todo(task, reasoning, priority, active_form, dependencies)

  async def execute_command(self, command: str, timeout: int = 30) -> CommandResult:
    """Execute a terminal command."""
    result = await self.command_executor.execute(command=command, timeout=timeout)
    return result.data

  async def process_request(self, user_request: str, file_contexts: List[Dict[str, str]]) -> LLMResponse:
    """Process a user request and generate edits."""
    messages = [
      {"role": "system", "content": self._build_system_prompt()},
      {"role": "user", "content": self._build_user_prompt(user_request, file_contexts)},
    ]

    result = await self.llm_client.execute(messages=messages, response_format={"type": "json_object"})

    if not result.success:
      raise Exception(f"LLM request failed: {result.error}")

    parsed = parse_llm_json(result.data)
    return LLMResponse(**parsed)

  def parse_edits(self, llm_response: LLMResponse) -> List[FileEdit]:
    """Parse edits from LLM response."""
    edits = []
    for edit_data in llm_response.edits:
      edit = FileEdit(
        file_path=edit_data["file_path"],
        old_content=edit_data["old_content"],
        new_content=edit_data["new_content"],
        description=edit_data["description"],
      )
      edits.append(edit)
    return edits

  async def generate_todo_plan(self, user_request: str, file_contexts: List[Dict[str, str]]) -> TodoPlan:
    """Generate a todo plan for the user request."""
    result = await self.todo_planner.execute(user_request=user_request, file_contexts=file_contexts)
    if not result.success:
      raise Exception(f"Todo planning failed: {result.error}")
    return result.data

  async def self_reflect(
    self,
    todo: Todo,
    user_request: str,
    file_contexts: List[Dict[str, str]],
    completed_todos: Optional[List[Todo]] = None,
  ) -> SelfReflection:
    """Perform self-reflection to plan next actions."""
    completed_todos = completed_todos or []
    completed_context = (
      "Previously completed todos:\n" + "\n".join([f"- {t.task}" for t in completed_todos]) + "\n\n" if completed_todos else ""
    )

    prompt = f"""
You are an AI agent thinking step-by-step about the next actions for a todo item.

Original user request: {user_request}
Current todo: {todo.task}
Reasoning: {todo.reasoning}

{completed_context}

Think step-by-step about what you need to do next and express it as deliberate action planning.

Respond with JSON containing:
- "current_state": A concise action statement starting with "Now I will..." (e.g., "Now I will create the test files", "Now I will implement the feature")
- "next_action_plan": A brief description of the specific actions you'll take, formatted as a clear action sequence
- "action_type": Primary type of actions needed - "edits", "commands", "searches", or "mixed"
- "confidence_level": Your confidence in the plan - "high", "medium", or "low"

Keep both statements concise and action-oriented. Focus on concrete actions like creating, modifying, or implementing code.
"""

    messages = [
      {
        "role": "system",
        "content": "You are an AI assistant that performs self-reflection and action planning. Respond ONLY with valid JSON.",
      },
      {"role": "user", "content": prompt},
    ]

    result = await self.llm_client.execute(messages, response_format={"type": "json_object"})
    default_reflection = SelfReflection(
      current_state="Error analyzing state", next_action_plan="Retry analysis", action_type="mixed", confidence_level="low"
    )

    if not result.success:
      return default_reflection

    try:
      parsed = parse_llm_json(result.data)
      return SelfReflection(
        current_state=str(parsed.get("current_state", "")),
        next_action_plan=str(parsed.get("next_action_plan", "")),
        action_type=str(parsed.get("action_type", "mixed")),
        confidence_level=str(parsed.get("confidence_level", "medium")),
      )
    except Exception:
      return default_reflection

  async def process_todo(
    self,
    todo: Todo,
    user_request: str,
    file_contexts: List[Dict[str, str]],
    completed_todos: Optional[List[Todo]] = None,
  ) -> TodoResult:
    """Process a single todo."""
    result = await self.todo_processor.execute(
      todo=todo, user_request=user_request, file_contexts=file_contexts, completed_todos=completed_todos or []
    )
    return result.data

  async def process_todo_progressive(
    self,
    todo: Todo,
    user_request: str,
    file_contexts: List[Dict[str, str]],
    completed_todos: Optional[List[Todo]] = None,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
  ) -> TodoResult:
    """Process a single todo progressively by breaking it into subtasks."""
    # First, get subtasks for this todo
    subtasks_result = await self.subtask_executor.plan_subtasks(todo, user_request, file_contexts)

    if not subtasks_result.success:
      # Fall back to regular processing
      return await self.process_todo(todo, user_request, file_contexts, completed_todos)

    subtasks = subtasks_result.data
    if not subtasks:
      # No subtasks, fall back to regular processing
      return await self.process_todo(todo, user_request, file_contexts, completed_todos)

    # Process each subtask sequentially
    edits = []
    completed_subtasks = []

    for subtask in sorted(subtasks, key=lambda x: x.get("order", 0)):
      # Notify about subtask start
      if progress_callback:
        progress_callback("subtask_start", subtask)

      # Execute the subtask
      try:
        edit_result = await self.subtask_executor.execute_subtask(subtask, todo, user_request, file_contexts, completed_subtasks)
      except Exception as e:
        # Create a failed result
        from .tools.base import ToolResult

        edit_result = ToolResult(success=False, error=str(e))

      if edit_result.success and edit_result.data:
        edit = edit_result.data
        edits.append(edit)
        completed_subtasks.append(subtask)

        # Notify about subtask completion with the edit
        if progress_callback:
          progress_callback("subtask_complete", {"subtask": subtask, "edit": edit})

    # Return a TodoResult with all the edits
    return TodoResult(
      thinking=f"Completed {len(edits)} subtasks for: {todo.task}",
      edits=edits,
      completed=len(edits) == len(subtasks),
      next_steps="" if len(edits) == len(subtasks) else f"Failed to complete {len(subtasks) - len(edits)} subtasks",
    )

  async def generate_edit_summary(self, applied_edits: List[FileEdit], user_request: str) -> str:
    """Generate a summary of applied edits."""
    result = await self.edit_summarizer.execute(applied_edits=applied_edits, user_request=user_request)
    return result.data

  def _build_system_prompt(self) -> str:
    """Build the system prompt for LLM requests."""
    return """You are an AI coding assistant. You MUST respond ONLY with valid JSON. Do not include any text before or after the JSON.

When given a user request and file context, respond with a structured JSON containing:
1. "summary": A brief description of changes you're making
2. "commands": (optional) A list of terminal commands to run, each with:
   - "command": The shell command to execute
   - "description": Why you're running this command
3. "searches": (optional) A list of search operations to find specific content, each with:
   - "query": What you're searching for (human-readable)
   - "command": The bash command to execute (grep, find, ripgrep, etc.)
   - "description": Why you need this search information
4. "edits": A list of file edits, each with:
   - "file_path": The path to the file to edit
   - "old_content": The exact content to replace (must match exactly, including whitespace). For NEW FILES, use empty string ""
   - "new_content": The new content to replace it with (or full file content for new files)
   - "description": A brief description of this specific edit

SEARCH GUIDELINES:
- Use searches when you need to find specific content, functions, patterns, or files
- Only search if the information isn't already in the provided file context
- Examples: "grep -r 'specific_function' .", "find . -name '*.py' | head -10", "rg 'pattern' --type python"
- Search commands run in the project root directory and results are displayed to help guide your edits

COMMAND EXECUTION GUIDELINES:
- Use commands to run tests, check syntax, or perform other operations
- Examples: "pytest tests/", "python -m flake8", "npm test"
- Commands run in the project root directory
- Commands help you understand the codebase before making changes
- Use commands to verify your changes work (run tests, check syntax, etc.)

IMPORTANT EDITING GUIDELINES:
- For NEW FILES: Use empty string "" for old_content
- For SMALL CHANGES: Find a specific section, paragraph, or lines to replace
- For COMPLETE FILE REWRITES: Use "REWRITE_ENTIRE_FILE" as old_content and put the new file content in new_content
- Copy old_content EXACTLY from the file context, including all whitespace and newlines
- When the user asks to rewrite, restructure, or make major changes to a file, use "REWRITE_ENTIRE_FILE" mode
- Break large changes into multiple smaller edits if doing targeted changes

Only make necessary changes to implement the user's request.
"""

  def _build_user_prompt(self, user_request: str, file_contexts: List[Dict[str, str]]) -> str:
    """Build the user prompt for LLM requests."""
    prompt_parts = [f"User request: {user_request}\n"]

    if file_contexts:
      prompt_parts.append("File contexts:")
      for ctx in file_contexts:
        prompt_parts.append(f"\n--- {ctx['path']} ---")
        prompt_parts.append(ctx["content"])
        prompt_parts.append("--- End ---\n")

    prompt_parts.append("\nRespond with valid JSON only.")
    return "\n".join(prompt_parts)
