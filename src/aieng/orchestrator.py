from typing import List

from rich.prompt import Confirm

from .ui import TerminalUI
from .diff import DiffProcessor
from .agent import Agent, FileEdit
from .context import FileContextManager


class AIAgentOrchestrator:
  def __init__(self, model: str = "grok-4", project_root: str = "."):
    self.ui = TerminalUI()
    self.context_manager = FileContextManager(project_root=project_root)
    self.diff_processor = DiffProcessor(project_root=project_root)
    self.config = self.load_config()
    
    # Use model from config if available, otherwise use provided default
    self.model = self.config.get("model", model)
    self.agent = Agent(model=self.model, ui_callback=self._ui_callback, project_root=project_root, config=self.config)
    
    # Update UI with auto-accept status
    self.ui.set_auto_accept(self.config.get("auto_accept", False))

  def _ui_callback(self, action: str, *args):
    """Callback for agent to show UI messages"""
    if action == "show_llm_retry":
      self.ui.show_llm_retry(*args)
    elif action == "show_llm_retry_success":
      self.ui.show_llm_retry_success(*args)
    elif action == "show_llm_retry_failed":
      self.ui.show_llm_retry_failed(*args)
    elif action == "show_command_execution":
      self.ui.show_command_execution(*args)
    elif action == "show_command_result":
      self.ui.show_command_result(*args)
    elif action == "start_loading":
      self.ui.start_loading(*args)
    elif action == "stop_loading":
      self.ui.stop_loading()

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

  async def process_user_request(self, user_request: str, specific_files: List[str] = None) -> bool:
    try:
      # Build context
      file_contexts = self.context_manager.build_context(user_request, specific_files)
      self.ui.show_analyzing_files(file_contexts)

      # Generate todo plan
      todo_plan = await self.agent.generate_todo_plan(user_request, file_contexts)
      self.ui.show_todo_plan(todo_plan.summary, todo_plan.todos)

      # Process todos sequentially with dependency handling
      completed_todos = []
      all_edits = []

      # Sort todos by dependencies (simple topological sort)
      remaining_todos = todo_plan.todos.copy()

      while remaining_todos:
        # Find todos with no unresolved dependencies
        ready_todos = [todo for todo in remaining_todos if all(dep_id in [ct.id for ct in completed_todos] for dep_id in todo.dependencies)]

        if not ready_todos:
          # If no todos are ready, pick the first one (dependency cycle or issue)
          ready_todos = [remaining_todos[0]]

        # Process the next ready todo
        current_todo = ready_todos[0]
        remaining_todos.remove(current_todo)

        self.ui.show_processing_todo(current_todo.id, current_todo.task)

        # Process the todo with chain-of-thought
        todo_result = await self.agent.process_todo(current_todo, user_request, file_contexts, completed_todos)

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
          from .agent import SearchResult
          search_results = []
          for search_data in todo_result.searches:
            query = search_data.get("query", "")
            command = search_data.get("command", "")
            description = search_data.get("description", f"Search for todo {current_todo.id}")
            
            if command:
              # Execute the search command and capture results
              command_result = await self.agent.execute_command(command)
              search_result = SearchResult(
                query=query,
                command=command,
                results=command_result.stdout if command_result.success else command_result.stderr,
                description=description
              )
              search_results.append(search_result)
          
          if search_results:
            # Show search results
            self.ui.show_multiple_searches(search_results)

        # Convert edits and collect them
        if todo_result.edits:
          edits = []
          for edit_data in todo_result.edits:
            edit = FileEdit(
              file_path=edit_data.get("file_path", ""),
              old_content=edit_data.get("old_content", ""),
              new_content=edit_data.get("new_content", ""),
              description=edit_data.get("description", f"Edit for todo {current_todo.id}"),
            )
            edits.append(edit)

          if edits:
            # Show diffs for this todo
            diff_previews = self.diff_processor.preview_edits(edits)
            self.ui.show_multiple_diffs(diff_previews, edits)

            # Get user confirmation
            auto_accept = hasattr(self, "config") and self.config.get("auto_accept", False)
            should_apply, auto_accept_enabled = self.ui.confirm_changes(auto_accept=auto_accept)
            
            # Update config if auto-accept was enabled
            if auto_accept_enabled:
              self.config["auto_accept"] = True
              self.save_config()

            if should_apply:
              # Apply edits for this todo
              self.ui.show_applying_changes()
              results = self.diff_processor.apply_edits(edits)

              successful_count = sum(1 for result in results if result.success)
              if successful_count == len(results):
                all_edits.extend(edits)
                self.ui.show_todo_completion(current_todo.id, True)
                completed_todos.append(current_todo)

                # Show updated todo list
                self.ui.show_todo_update_header()
                for todo in todo_plan.todos:
                  is_completed = todo.id in [ct.id for ct in completed_todos]
                  self.ui.show_todo_status(todo.id, todo.task, is_completed)
                self.ui.show_todo_update_complete()
              else:
                first_failure = next(result for result in results if not result.success)
                self.ui.show_error(f"Failed to apply edits for todo {current_todo.id}: {first_failure.error}")

                # Try to reprocess the todo with a hint about the error
                self.ui.show_step(f"Retrying todo {current_todo.id} with error context")

                # Add error context to help the LLM fix the issue
                error_context = f"Previous attempt failed with error: {first_failure.error}. Please use 'REWRITE_ENTIRE_FILE' for old_content when modifying existing files."

                try:
                  retry_result = await self.agent.process_todo(
                    current_todo, f"{user_request}\n\nError context: {error_context}", file_contexts, completed_todos
                  )

                  # Execute commands in retry if any
                  if retry_result.commands:
                    for cmd_data in retry_result.commands:
                      command = cmd_data.get("command", "")
                      if command:
                        await self.agent.execute_command(command)

                  if retry_result.edits:
                    retry_edits = []
                    for edit_data in retry_result.edits:
                      edit = FileEdit(
                        file_path=edit_data.get("file_path", ""),
                        old_content=edit_data.get("old_content", ""),
                        new_content=edit_data.get("new_content", ""),
                        description=edit_data.get("description", f"Retry edit for todo {current_todo.id}"),
                      )
                      retry_edits.append(edit)

                    # Try applying the retry edits
                    retry_results = self.diff_processor.apply_edits(retry_edits)
                    retry_successful = sum(1 for r in retry_results if r.success)

                    if retry_successful == len(retry_results):
                      all_edits.extend(retry_edits)
                      self.ui.show_todo_completion(current_todo.id, True)
                      completed_todos.append(current_todo)

                      # Show updated todo list
                      self.ui.show_todo_update_header()
                      for todo in todo_plan.todos:
                        is_completed = todo.id in [ct.id for ct in completed_todos]
                        self.ui.show_todo_status(todo.id, todo.task, is_completed)
                      self.ui.show_todo_update_complete()
                    else:
                      self.ui.show_todo_completion(current_todo.id, False, "Retry also failed, skipping")
                      continue
                  else:
                    self.ui.show_todo_completion(current_todo.id, False, "No retry edits generated, skipping")
                    continue

                except Exception as retry_error:
                  self.ui.show_error(f"Retry failed: {retry_error}")
                  self.ui.show_todo_completion(current_todo.id, False, "Retry failed, skipping")
                  continue
            else:
              self.ui.show_rejection()
              return False
        else:
          # No edits needed for this todo
          self.ui.show_todo_completion(current_todo.id, todo_result.completed, todo_result.next_steps)
          if todo_result.completed:
            completed_todos.append(current_todo)

            # Show updated todo list
            self.ui.show_todo_update_header()
            for todo in todo_plan.todos:
              is_completed = todo.id in [ct.id for ct in completed_todos]
              self.ui.show_todo_status(todo.id, todo.task, is_completed)
            self.ui.show_todo_update_complete()

      # Generate final summary only if edits were applied
      if all_edits:
        self.ui.show_generating_summary()
        summary = await self.agent.generate_edit_summary(all_edits, user_request)
        self.ui.show_edit_summary(summary)
        self.ui.show_success(len(all_edits))
      elif completed_todos:
        # If todos completed but no edits were needed
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

    # Line 3: model name
    line3_content = f"   Model: {self.model}"
    line3_padding = box_width - len(line3_content)

    # Line 4: auto-accept status
    auto_accept_status = "enabled" if self.config.get("auto_accept", False) else "disabled"
    line4_content = f"   Auto-accept: {auto_accept_status}"
    line4_padding = box_width - len(line4_content)

    # Line 5: API base URL
    api_base_url = self.config.get("api_base_url", "https://api.x.ai/v1")
    line5_content = f"   API: {api_base_url}"
    line5_padding = box_width - len(line5_content)

    # Line 6: current directory
    line6_content = f"   Directory: {current_dir}"
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

    # Model line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line3_content, style="#666666")
    welcome_text.append(" " * line3_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Auto-accept line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line4_content, style="#666666")
    welcome_text.append(" " * line4_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # API line
    welcome_text.append("│", style="#EB999A")
    welcome_text.append(line5_content, style="#666666")
    welcome_text.append(" " * line5_padding, style="#EB999A")
    welcome_text.append("│\n", style="#EB999A")

    # Directory line
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
    allowed_models = ["grok-3", "grok-4"]
    if new_model not in allowed_models:
      self.ui.console.print(f"[red]Error: Model '{new_model}' not supported. Allowed models: {', '.join(allowed_models)}[/red]")
      return
    
    # Update model
    self.model = new_model
    self.config["model"] = new_model
    
    # Recreate agent with new model
    self.agent = Agent(model=new_model, ui_callback=self._ui_callback, project_root=self.context_manager.project_root, config=self.config)
    
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

  async def run_single_request(self, request: str, files: List[str] = None) -> bool:
    return await self.process_user_request(request, files)
