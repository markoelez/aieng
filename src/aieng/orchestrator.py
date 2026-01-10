from typing import List, Optional

from .ui import TerminalUI
from .diff import DiffProcessor
from .agent import Agent
from .config import DEFAULT_MODEL, SUPPORTED_MODELS, DEFAULT_API_BASE_URL
from .models import FileEdit, SearchResult
from .context import FileContextManager
from .todo_manager import TodoManager


class AIAgentOrchestrator:
  def __init__(self, model: str = DEFAULT_MODEL, project_root: str = "."):
    self.ui = TerminalUI()
    self.context_manager = FileContextManager(project_root=project_root)
    self.diff_processor = DiffProcessor(project_root=project_root)
    self.config = self.load_config()

    # Use model from config if available, otherwise use provided default
    self.model = self.config.get("model", model)
    self.agent = Agent(model=self.model, ui_callback=self._ui_callback, project_root=project_root, config=self.config)

    # Initialize TodoManager for centralized state tracking
    self.todo_manager = TodoManager(ui_callback=self._todo_ui_callback)

    # Connect agent to TodoManager for dynamic todo modification
    self.agent.set_todo_manager(self.todo_manager)

    # Update UI with auto-accept status
    self.ui.set_auto_accept(self.config.get("auto_accept", False))

  def _ui_callback(self, action: str, *args):
    """Callback for agent to show UI messages"""
    action_map = {
      "show_llm_retry": self.ui.show_llm_retry,
      "show_llm_retry_success": self.ui.show_llm_retry_success,
      "show_llm_retry_failed": self.ui.show_llm_retry_failed,
      "show_command_execution": self.ui.show_command_execution,
      "show_command_result": self.ui.show_command_result,
      "start_loading": self.ui.start_loading,
    }
    if action in action_map:
      action_map[action](*args)
    elif action == "stop_loading":
      self.ui.stop_loading()

  def _todo_ui_callback(self, event: str, data: dict):
    """Callback for TodoManager to update UI on state changes."""
    event_handlers = {
      "plan_set": lambda: self.ui.show_todo_list(data["todos"], current_todo_id=None),
      "todo_added": lambda: self.ui.show_todo_added(data["todo"]),
    }
    if event in event_handlers:
      event_handlers[event]()

  def load_config(self) -> dict:
    """Load configuration from aieng.toml if it exists."""
    import os

    import tomli

    config_path = os.path.join(self.diff_processor.project_root, "aieng.toml")
    if os.path.exists(config_path):
      with open(config_path, "rb") as f:
        return tomli.load(f)
    return {}

  def save_config(self):
    """Save configuration to aieng.toml."""
    import os

    import tomli_w

    config_path = os.path.join(self.diff_processor.project_root, "aieng.toml")
    with open(config_path, "wb") as f:
      tomli_w.dump(self.config, f)

  async def process_user_request(self, user_request: str, specific_files: Optional[List[str]] = None) -> bool:
    """Process a user request using a tight agentic loop pattern.

    The loop follows Claude Code's pattern:
    1. Create a plan with todos
    2. Display the todo list
    3. Pick next todo, mark in_progress
    4. Execute the todo
    5. Mark completed, update UI
    6. Loop until all complete
    """
    try:
      # Build context
      file_contexts = self.context_manager.build_context(user_request, specific_files)
      self.ui.show_analyzing_files(file_contexts)

      # Step 1: Create plan with todos
      todo_plan = await self.agent.generate_todo_plan(user_request, file_contexts)

      # Initialize TodoManager with the plan
      self.todo_manager.set_plan(todo_plan)

      all_edits = []

      # Step 2-6: Tight agentic loop - process todos until complete
      while self.todo_manager.has_remaining_work():
        # Get the next ready todo
        current_todo = self.todo_manager.get_next_todo()

        if current_todo is None:
          # Check for dependency cycles or no ready todos
          pending = self.todo_manager.get_pending_todos()
          if pending:
            # Force pick the first pending todo to break cycle
            current_todo = pending[0]
          else:
            break

        # Mark todo as in_progress (this triggers UI update)
        self.todo_manager.mark_in_progress(current_todo.id)

        # Show what we're working on
        self.ui.show_processing_todo(current_todo.id, current_todo.task)

        # Self-Reflection - Plan next actions
        completed_todos = self.todo_manager.get_completed_todos()
        self_reflection = await self.agent.self_reflect(current_todo, user_request, file_contexts, completed_todos)
        self.ui.show_self_reflection(self_reflection)

        # Execute Actions - Process the todo with progressive subtask execution
        first_subtask = True

        def progress_callback(event_type, data):
          nonlocal first_subtask
          if event_type == "subtask_start":
            first_subtask = False
            self.ui.show_step(f"Starting: {data['description']}")
          elif event_type == "subtask_complete":
            subtask = data["subtask"]
            edit = data["edit"]
            self.ui.show_step(f"Generated: {subtask['description']}", is_final=True)

            # Show the diff immediately after generation
            edit_obj = FileEdit(
              file_path=edit.get("file_path", ""),
              old_content=edit.get("old_content", ""),
              new_content=edit.get("new_content", ""),
              description=edit.get("description", ""),
            )
            diff_preview = self.diff_processor.preview_edits([edit_obj])[0]
            is_new_file = not edit_obj.old_content.strip()
            self.ui.show_diff_header(edit_obj.file_path, edit_obj.description, is_new_file)
            self.ui.show_diff_content(diff_preview)

            # Apply the edit immediately
            auto_accept = hasattr(self, "config") and self.config.get("auto_accept", False)
            if auto_accept:
              self.ui.show_applying_changes()
              results = self.diff_processor.apply_edits([edit_obj])
              if results[0].success:
                all_edits.append(edit_obj)
                self.ui.show_success(1)
              else:
                self.ui.show_error(f"Failed to apply edit to {edit_obj.file_path}: {results[0].error}")
            else:
              should_apply, _, _ = self.ui.confirm_single_file_change(edit_obj.file_path, auto_accept=False)
              if should_apply:
                self.ui.show_applying_changes()
                results = self.diff_processor.apply_edits([edit_obj])
                if results[0].success:
                  all_edits.append(edit_obj)
                  self.ui.show_success(1)
                else:
                  self.ui.show_error(f"Failed to apply edit to {edit_obj.file_path}: {results[0].error}")

        # Process the todo
        todo_result = await self.agent.process_todo_progressive(
          current_todo, user_request, file_contexts, completed_todos, progress_callback
        )

        # Show the thinking process
        self.ui.show_todo_thinking(todo_result.thinking)

        # Execute commands if any
        if todo_result.commands:
          for cmd_data in todo_result.commands:
            command = cmd_data.get("command", "")
            if command:
              await self.agent.execute_command(command)

        # Execute searches if any
        if todo_result.searches:
          search_results = []
          for search_data in todo_result.searches:
            query = search_data.get("query", "")
            command = search_data.get("command", "")
            description = search_data.get("description", f"Search for todo {current_todo.id}")

            if command:
              command_result = await self.agent.execute_command(command)
              search_result = SearchResult(
                query=query,
                command=command,
                results=command_result.stdout if command_result.success else command_result.stderr,
                description=description,
              )
              search_results.append(search_result)

          if search_results:
            self.ui.show_multiple_searches(search_results)

        # Mark todo as completed (this triggers UI update)
        self.todo_manager.mark_completed(current_todo.id)
        self.ui.show_todo_completion(current_todo.id, True)

      # Generate final summary
      if all_edits:
        self.ui.show_generating_summary()
        summary = await self.agent.generate_edit_summary(all_edits, user_request)
        self.ui.show_edit_summary(summary)
        self.ui.show_success(len(all_edits))
      elif self.todo_manager.is_all_completed():
        self.ui.show_step("All todos completed", is_final=True)

      return True

    except Exception as e:
      self.ui.show_error(str(e))
      return False

  async def run_interactive_session(self):
    # Show welcome message
    import os

    from rich.console import Console

    console = Console()
    current_dir = os.getcwd()

    # Calculate padding to ensure proper alignment
    box_width = 65  # Total internal width (between │ characters) - increased for more content

    # Line 1: "✻ Welcome to AIEng!"
    line1_content = " ✻ Welcome to AIENG!"
    line1_padding = box_width - len(line1_content)

    # Line 3: API base URL
    api_base_url = self.config.get("api_base_url", DEFAULT_API_BASE_URL)
    line3_content = f"   API: {api_base_url}"
    line3_padding = box_width - len(line3_content)

    # Line 4: model name
    line4_content = f"   Model: {self.model}"
    line4_padding = box_width - len(line4_content)

    # Line 5: current directory
    line5_content = f"   Directory: {current_dir}"
    line5_padding = box_width - len(line5_content)

    # Line 6: auto-accept status
    auto_accept_status = "enabled" if self.config.get("auto_accept", False) else "disabled"
    line6_content = f"   Auto-accept: {auto_accept_status}"
    line6_padding = box_width - len(line6_content)

    # Create the welcome message with mixed colors
    from rich.text import Text

    welcome_text = Text()

    # Top border
    welcome_text.append("╭─────────────────────────────────────────────────────────────────╮\n", style="#EB999A")

    # Title line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line1_content, style="#EB999A")
    welcome_text.append(" " * line1_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Empty line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(" " * box_width, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # API line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line3_content, style="#666666")
    welcome_text.append(" " * line3_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Model line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line4_content, style="#666666")
    welcome_text.append(" " * line4_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Directory line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line5_content, style="#666666")
    welcome_text.append(" " * line5_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Auto-accept line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line6_content, style="#666666")
    welcome_text.append(" " * line6_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Bottom border
    welcome_text.append("╰─────────────────────────────────────────────────────────────────╯", style="#EB999A")

    console.print(welcome_text)
    console.print()

    while True:
      try:
        user_request = self.ui.get_user_request()

        if user_request is None or user_request.lower() in ["quit", "exit", "q"]:
          break

        if not user_request.strip():
          continue

        # Handle model change command
        if user_request.startswith("__MODEL_CHANGE__"):
          new_model = user_request.replace("__MODEL_CHANGE__", "")
          await self.change_model(new_model)
          continue

        # Handle auto-accept toggle command
        if user_request.startswith("__AUTO_TOGGLE__"):
          new_auto_state = user_request.replace("__AUTO_TOGGLE__", "") == "True"
          await self.toggle_auto_accept(new_auto_state)
          continue

        await self.process_user_request(user_request)

      except KeyboardInterrupt:
        # Double Ctrl+C - graceful exit (handled in UI)
        break
      except EOFError:
        break

  async def change_model(self, new_model: str):
    """Change the active model and persist to config"""
    # Validate model
    if new_model not in SUPPORTED_MODELS:
      self.ui.console.print(f"[red]Error: Model '{new_model}' not supported. Allowed models: {', '.join(SUPPORTED_MODELS)}[/red]")
      return

    # Update model
    self.model = new_model
    self.config["model"] = new_model

    # Recreate agent with new model
    self.agent = Agent(
      model=new_model,
      ui_callback=self._ui_callback,
      project_root=str(self.context_manager.project_root),
      config=self.config,
    )

    # Save config
    self.save_config()

    # Update welcome display with new model
    self.ui.console.print(f"[#60875F]● Model changed to {new_model}[/#60875F]")

  async def toggle_auto_accept(self, new_state: bool):
    """Toggle auto-accept setting and persist to config"""
    # Update auto-accept setting
    self.config["auto_accept"] = new_state
    self.ui.set_auto_accept(new_state)

    # Save config
    self.save_config()

    state_text = "enabled" if new_state else "disabled"
    self.ui.console.print(f"[#60875F]● Auto-accept setting saved: {state_text}[/#60875F]")

  async def run_single_request(self, request: str, files: Optional[List[str]] = None) -> bool:
    return await self.process_user_request(request, files)
