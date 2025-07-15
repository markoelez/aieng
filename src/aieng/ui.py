import sys
import time
import signal
import asyncio
import readline
import threading
from typing import List

from rich.live import Live
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.console import Console

from .models import FileEdit


class TerminalUI:
  def __init__(self):
    self.console = Console()
    self.loading_live = None
    self.loading_task = None
    self.loading_active = False
    self.last_interrupt_time = 0
    self.interrupt_count = 0
    self.input_has_text = False
    self.auto_accept = False
    self.commands_visible = False
    self.show_tips = True

  def show_welcome(self):
    pass

  def set_auto_accept(self, enabled: bool):
    """Set the auto-accept status for UI display"""
    self.auto_accept = enabled

  def _get_cursor_offset(self):
    """Get the number of lines to account for auto-accept indicator"""
    return 1 if self.auto_accept else 0

  def _show_command_menu(self):
    """Show the command menu under the input box"""
    commands = [
      ("/init", "Create a aieng.toml file with configuration settings"),
      ("/model", "Switch between available AI models (grok-3, grok-4)"),
      ("/auto", "Toggle auto-accept edits on/off"),
      ("/help", "Show help and available commands"),
      ("/exit", "Exit the AIENG tool"),
      ("/clear", "Clear the screen and start fresh"),
    ]

    # Use Rich console for proper formatting
    for cmd, description in commands:
      self.console.print(f"  [bright_white]{cmd:<16}[/bright_white] [white]{description}[/white]")
    self.commands_visible = True

  def get_user_request(self) -> str:
    while True:
      # Get terminal width
      terminal_width = self.console.size.width
      box_width = terminal_width - 2  # Account for left/right borders

      # Show tips only on initial load
      if self.show_tips:
        tips_text = Text()
        tips_text.append("Tips for getting started:", style="#666666")
        self.console.print(tips_text)
        self.console.print()

        tip_1 = Text()
        tip_1.append(" 1. Type / to see available commands", style="#666666")
        self.console.print(tip_1)

        tip_2 = Text()
        tip_2.append(" 2. Use AIENG to help with complex, multi-file edits", style="#666666")
        self.console.print(tip_2)

        tip_3 = Text()
        tip_3.append(" 3. Be as specific as you would with another engineer for the best results", style="#666666")
        self.console.print(tip_3)
        self.console.print()

        self.show_tips = False  # Don't show tips again

      # Create box lines with colored borders
      # Create colored box components
      top_line = Text()
      top_line.append("╭" + "─" * box_width + "╮", style="#464646")

      input_line = Text()
      input_line.append("│ ", style="#464646")
      input_line.append(">", style="bright_white")
      input_line.append(" ", style="#464646")
      # Add placeholder hint in light gray
      hint_text = 'Try "add tests to this project"'
      input_line.append(hint_text, style="#666666")
      remaining_space = box_width - 3 - len(hint_text)
      if remaining_space > 0:
        input_line.append(" " * remaining_space, style="#464646")
      input_line.append("│", style="#464646")

      bottom_line = Text()
      bottom_line.append("╰" + "─" * box_width + "╯", style="#464646")

      self.console.print(top_line)
      self.console.print(input_line)
      self.console.print(bottom_line)

      # Show auto-accept indicator if enabled
      if self.auto_accept:
        auto_accept_line = Text()
        auto_accept_line.append("⏵⏵ auto-accept edits on", style="bold #BDBDFE")  # Purple
        self.console.print(auto_accept_line)

      # Move cursor up to input position
      lines_to_move_up = 3 if self.auto_accept else 2
      sys.stdout.write(f"\033[{lines_to_move_up}A")  # Move up to input box
      sys.stdout.write("\033[4C")  # Move right 4 characters (after "│ > ")
      sys.stdout.flush()

      # Custom input handling without using input() to avoid newlines on Ctrl+C
      user_input = ""
      hint_cleared = False

      while True:
        try:
          # Read single character
          import tty
          import termios

          # Save terminal settings
          old_settings = termios.tcgetattr(sys.stdin)
          tty.setraw(sys.stdin.fileno())

          char = sys.stdin.read(1)

          # Restore terminal settings
          termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

          # Handle different characters
          if ord(char) == 3:  # Ctrl+C
            if user_input.strip():
              # Clear current input and reset
              user_input = ""
              hint_cleared = False  # Reset hint state
              self.interrupt_count = 1
              # Redraw clean input line with colors preserved (#464646)
              sys.stdout.write("\r")
              sys.stdout.write(" " * (box_width + 2))  # Clear entire line
              sys.stdout.write("\r")
              # Redraw the input line with original colors and hint
              hint_text = 'Try "add tests to this project"'
              sys.stdout.write(
                f"\033[38;2;70;70;70m│ \033[97m> \033[38;5;242m{hint_text}"
                + " " * (box_width - 3 - len(hint_text))
                + "\033[38;2;70;70;70m│\033[0m"
              )
              sys.stdout.write(f"\r\033[38;2;70;70;70m│ \033[97m> \033[0m")
              sys.stdout.flush()
              # Show quit hint after clearing input
              sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past the box
              sys.stdout.write("\r")  # Move to start of line
              sys.stdout.flush()
              self.console.print("[#666666]Press ctrl-c again to quit[/#666666]")
              # Move back up to input position
              sys.stdout.write(f"\033[{3 + self._get_cursor_offset()}A")  # Move up lines (past hint and box)
              sys.stdout.write("\033[4C")  # Move right to input position
              sys.stdout.flush()
            else:
              # Empty input - count interrupt
              self.interrupt_count += 1
              if self.interrupt_count >= 2:
                # Clear the hint first, then exit gracefully
                sys.stdout.write("\033[2B")  # Move past box
                sys.stdout.write("\r")  # Move to start of line
                sys.stdout.write("\033[K")  # Clear line (removes hint)
                sys.stdout.flush()
                self.console.print("[bright_white]Goodbye![/bright_white]")
                sys.exit(0)
              else:
                # First Ctrl+C on empty - show quit hint
                # Move past the box and show hint
                sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past the box
                sys.stdout.write("\r")  # Move to start of line
                sys.stdout.flush()
                self.console.print("[#666666]Press ctrl-c again to quit[/#666666]")
                # Move back up to input position
                sys.stdout.write(f"\033[{3 + self._get_cursor_offset()}A")  # Move up lines (past hint and box)
                sys.stdout.write("\033[4C")  # Move right to input position
                sys.stdout.flush()

          elif ord(char) == 13:  # Enter
            # Clear quit hint if it's showing
            if self.interrupt_count == 1:
              # Clear the hint line first
              sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past box
              sys.stdout.write("\r")  # Move to start of line
              sys.stdout.write("\033[K")  # Clear line (removes hint)
              sys.stdout.write("\r")  # Move to start of line
              sys.stdout.flush()
            else:
              # Move cursor down past the box to start of line
              sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past the box
              sys.stdout.write("\r")  # Move to start of line
              sys.stdout.flush()
            self.interrupt_count = 0  # Reset on successful input

            # Hide command menu before processing any input
            if self.commands_visible:
              # Move to where the command menu starts and clear it
              sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past input box
              sys.stdout.write("\r")  # Move to start of line
              for _ in range(6):  # Clear 6 command lines
                sys.stdout.write("\033[K")  # Clear current line
                sys.stdout.write("\033[B")  # Move down to next line
              # Move back to the line after the input box where command output will appear
              sys.stdout.write(f"\033[{6}A")  # Move back up 6 lines
              sys.stdout.write("\r")  # Move to start of line
              sys.stdout.flush()
              self.commands_visible = False

            # Check for commands
            command = user_input.strip()
            if command == "/init":
              self._handle_init_command()
              break  # Break out of character loop to restart input box
            elif command == "/model":
              result = self._handle_model_command()
              if result:
                return result  # Return model change request
              break
            elif command == "/auto":
              result = self._handle_auto_command()
              if result:
                return result  # Return auto-accept toggle request
              break
            elif command == "/help":
              self._handle_help_command()
              break
            elif command == "/exit":
              self._handle_exit_command()
              return None  # Signal to exit
            elif command == "/clear":
              self._handle_clear_command()
              break

            # Add blank line for separation before agent output (only for regular input)
            self.console.print()
            return user_input

          elif ord(char) == 127:  # Backspace
            if user_input:
              # Hide command menu if we're deleting the "/"
              if user_input == "/" and self.commands_visible:
                # First, delete the "/" character from the display
                sys.stdout.write("\b \b")
                sys.stdout.flush()

                # Clear the command menu by moving down and clearing lines
                sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past input box
                sys.stdout.write("\r")  # Move to start of line
                for _ in range(6):  # Clear 6 command lines
                  sys.stdout.write("\033[K")  # Clear current line
                  sys.stdout.write("\033[B")  # Move down to next line
                # Move back up to input position
                sys.stdout.write(f"\033[{2 + self._get_cursor_offset() + 6}A")  # Move back up
                sys.stdout.write("\033[4C")  # Move right to cursor position (after "│ > ")
                sys.stdout.flush()
                self.commands_visible = False

                # Remove from user_input
                user_input = user_input[:-1]
              else:
                # Normal backspace handling
                user_input = user_input[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()

          elif ord(char) >= 32:  # Printable characters
            # Clear quit hint if it's showing
            if self.interrupt_count == 1:
              self.interrupt_count = 0  # Reset interrupt count
              # Clear the hint line below
              sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past box
              sys.stdout.write("\r")  # Move to start of line
              sys.stdout.write("\033[K")  # Clear line (removes hint)
              sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}A")  # Move back up to input position
              sys.stdout.write("\033[4C")  # Move right to input position
              sys.stdout.flush()

            # Clear hint on first character typed
            if not hint_cleared:
              hint_cleared = True
              # Clear the line and redraw without hint but preserve border colors (#464646)
              sys.stdout.write("\r")
              # Move to start of line and clear, then redraw with ANSI colors matching #464646
              sys.stdout.write("\033[38;2;70;70;70m│ \033[97m> \033[0m" + " " * (box_width - 3) + "\033[38;2;70;70;70m│\033[0m")
              sys.stdout.write("\r\033[38;2;70;70;70m│ \033[97m> \033[0m")
              sys.stdout.flush()

            # Check if we have room (account for borders and prompt)
            max_input_length = box_width - 3  # "│ > " takes 3 chars, "│" takes 1
            if len(user_input) < max_input_length - 1:
              user_input += char
              sys.stdout.write(char)
              sys.stdout.flush()

              # Handle command menu display
              if user_input == "/" and not self.commands_visible:
                # Show command menu when "/" is typed
                # Save current cursor position
                cursor_position = len(user_input) + 4  # After "│ > /"

                # Move down past input box and auto-accept indicator
                sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past box
                sys.stdout.write("\r")  # Move to start of line
                sys.stdout.flush()

                # Show command menu using Rich console
                self._show_command_menu()

                # Move back up to input position
                lines_to_move_up = 2 + self._get_cursor_offset() + 6  # Box + auto-accept + 6 command lines
                sys.stdout.write(f"\033[{lines_to_move_up}A")  # Move back up
                sys.stdout.write(f"\033[{cursor_position}C")  # Move right to cursor position
                sys.stdout.flush()
              elif self.commands_visible and not user_input.startswith("/"):
                # Hide command menu if user types something other than commands after "/"
                # Clear the command menu by moving down and clearing lines
                sys.stdout.write(f"\033[{2 + self._get_cursor_offset()}B")  # Move down past input box
                sys.stdout.write("\r")  # Move to start of line
                for _ in range(6):  # Clear 6 command lines
                  sys.stdout.write("\033[K")  # Clear current line
                  sys.stdout.write("\033[B")  # Move down to next line
                # Move back up to input position
                sys.stdout.write(f"\033[{2 + self._get_cursor_offset() + 6}A")  # Move back up
                sys.stdout.write(f"\033[{len(user_input) + 4}C")  # Move right to cursor position
                sys.stdout.flush()
                self.commands_visible = False

        except Exception:
          # Fallback - break out of character loop and retry the whole input box
          break

  def show_step(self, step_text: str, is_final: bool = False):
    """Show a streaming step like Claude Code"""
    bullet = "●" if not is_final else "●"
    color = "white" if not is_final else "green"
    self.console.print(f"[{color}]{bullet}[/{color}] [bold bright_white]{step_text}[/bold bright_white]")

  def show_analyzing_files(self, file_contexts: List[dict]):
    if not file_contexts:
      return

    self.show_step("Analyzing Files")
    for ctx in file_contexts:
      self.console.print(f"  [white]• {ctx['path']}[/white]")
    self.console.print()  # Add spacing after file list

  def show_reading_file(self, file_path: str, description: str = ""):
    """Show when a file is being read"""
    self.show_read_header(file_path, description or "Reading file contents")

  def show_generating_response(self):
    self.show_step("Generating Response")
    self.console.print()  # Add spacing after step

  def show_search_header(self, query: str, search_description: str):
    """Show search in Claude Code style"""
    self.console.print()
    # Custom formatting for Search header - only "Search" is bold
    bullet = "●"
    self.console.print(f"[#60875F]{bullet}[/#60875F] [bold bright_white]Search[/bold bright_white]([bright_white]{query}[/bright_white])")
    self.console.print(f"  [white]⎿  {search_description}[/white]")
    self.console.print()  # Add spacing before search content

  def show_search_content(self, command: str, results: str):
    """Show the actual search command and results"""
    if not results.strip():
      return

    # Show the command that was executed
    self.console.print(f"       [bright_white]Command: {command}[/bright_white]")
    self.console.print()

    # Show search results with proper formatting
    lines = results.split("\n")
    for line in lines:
      if line.strip():
        self.console.print(f"         [white]{line}[/white]")
    self.console.print()  # Add spacing after search results

  def show_diff_header(self, file_path: str, edit_description: str, is_new_file: bool = False):
    """Show diff in Claude Code style"""
    self.console.print()
    # Custom formatting for operation header - only the operation type is bold
    bullet = "⏺"
    if is_new_file:
      operation = "Write"
    else:
      operation = "Update"
    self.console.print(
      f"[white]{bullet}[/white] [bold bright_white]{operation}[/bold bright_white]([bright_white]{file_path}[/bright_white])"
    )
    self.console.print(f"  [white]⎿  {edit_description}[/white]")

  def show_diff_content(self, diff_text: str):
    """Show the actual diff content with line numbers and changes in Claude Code style"""
    if not diff_text.strip():
      return

    lines = diff_text.split("\n")
    old_line_num = None
    new_line_num = None

    # Check for line number information
    has_line_numbers = any(line.startswith("@@") for line in lines)

    if not has_line_numbers:
      # Fallback: start from line 1 if no line number info available
      new_line_num = 1
      old_line_num = 1

    for line in lines:
      if line.startswith("@@"):
        # Parse line numbers from @@ header like @@ -481,1 +481,1 @@
        import re

        match = re.search(r"@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)(?:,\d+)?\s*@@", line)
        if match:
          old_line_num = int(match.group(1))
          new_line_num = int(match.group(2))
        continue
      elif line.startswith("+++") or line.startswith("---"):
        # Skip file headers
        continue
      elif line.startswith("+") and not line.startswith("+++"):
        # Added line - custom green background with white text starting after line numbers
        line_content = line[1:] if len(line) > 1 else ""
        self.console.print(
          f"       [white]{new_line_num:>3}[/white] [white on #60875F]+ {line_content}[/white on #60875F]",
          overflow="ellipsis",
          no_wrap=True,
        )
        if new_line_num is not None:
          new_line_num += 1
      elif line.startswith("-") and not line.startswith("---"):
        # Removed line - custom red background with white text starting after line numbers
        line_content = line[1:] if len(line) > 1 else ""
        self.console.print(
          f"       [white]{old_line_num:>3}[/white] [white on #875F5F]- {line_content}[/white on #875F5F]",
          overflow="ellipsis",
          no_wrap=True,
        )
        if old_line_num is not None:
          old_line_num += 1
      elif line.startswith(" "):
        # Context line - regular text
        line_content = line[1:] if len(line) > 1 else ""
        self.console.print(
          f"       [white]{new_line_num:>3}[/white]            [white]{line_content}[/white]", overflow="ellipsis", no_wrap=True
        )
        if new_line_num is not None:
          new_line_num += 1
        if old_line_num is not None:
          old_line_num += 1
      elif line.strip():
        # Handle any other non-empty lines that don't match expected patterns
        self.console.print(f"               [white]{line}[/white]")

  def show_multiple_searches(self, search_results: List):
    """Show multiple search operations"""
    for i, search_result in enumerate(search_results):
      if i > 0:
        self.console.print()  # Add spacing between multiple searches
      self.show_search_header(search_result.query, search_result.description)
      self.show_search_content(search_result.command, search_result.results)
      time.sleep(0.1)  # Small delay for streaming effect
    self.console.print()  # Add spacing after all searches

  def show_multiple_diffs(self, diff_previews: List[str], edits: List[FileEdit]):
    for i, (diff_text, edit) in enumerate(zip(diff_previews, edits)):
      if i > 0:
        self.console.print()  # Add spacing between multiple diffs
      # Check if this is a new file (empty old_content)
      is_new_file = not edit.old_content.strip()
      self.show_diff_header(edit.file_path, edit.description, is_new_file)
      self.show_diff_content(diff_text)
      time.sleep(0.1)  # Small delay for streaming effect
    self.console.print()  # Add spacing after all diffs

  def show_summary(self, summary: str, num_edits: int):
    """Show summary in Claude Code style"""
    self.console.print()
    self.show_step("Summary")
    self.console.print(f"  [white]Proposed {num_edits} edit(s): {summary}[/white]")
    self.console.print()  # Add spacing after summary

  def confirm_changes(self, auto_accept: bool = False) -> tuple[bool, bool]:
    """
    Returns (should_apply, auto_accept_enabled)
    """
    self.console.print()
    if auto_accept:
      self.console.print("[bright_white]Auto-accepting changes due to enabled setting.[/bright_white]")
      return (True, False)  # Apply changes, no change to auto-accept setting
    self.console.print("[bright_white]Apply these changes?[/bright_white]")
    self.console.print("[bright_white]1. Yes, apply changes[/bright_white]")
    self.console.print("[bright_white]2. No, reject changes[/bright_white]")
    choice = Prompt.ask("Enter your choice (1-2)", choices=["1", "2"], default="2")
    if choice == "1":
      self.console.print("[bright_white]Enable auto-accept for future edits?[/bright_white]")
      self.console.print("[bright_white]1. Yes, enable auto-accept[/bright_white]")
      self.console.print("[bright_white]2. No, ask each time[/bright_white]")
      auto_choice = Prompt.ask("Enter your choice (1-2)", choices=["1", "2"], default="2")
      auto_accept_enabled = auto_choice == "1"
      if auto_accept_enabled:
        self.set_auto_accept(True)
      return (True, auto_accept_enabled)
    return (False, False)

  def show_applying_changes(self):
    self.show_step("Applying Changes")
    self.console.print()  # Add spacing after step

  def show_success(self, num_edits: int):
    self.console.print()
    self.show_step(f"Successfully applied {num_edits} edit(s)", is_final=True)
    self.console.print()  # Add spacing after success

  def show_generating_summary(self):
    self.show_step("Generating Summary")
    self.console.print()  # Add spacing after step

  def show_edit_summary(self, summary: str):
    self.console.print()
    self.show_step("Summary", is_final=True)
    # Display the bulleted list of edits
    for line in summary.split("\n"):
      if line.strip():
        self.console.print(f"  [white]{line}[/white]")
    self.console.print()  # Add spacing after summary

  def show_planning(self):
    self.show_step("Planning")
    self.console.print()  # Add spacing after step

  def show_todo_plan(self, plan_summary: str, todos, current_todo_id=None, completed_todo_ids=None):
    self.console.print()
    # Custom formatting for Update Todos header
    bullet = "⏺"
    self.console.print(f"[white]{bullet}[/white] [bold bright_white]Update Todos[/bold bright_white]")

    if completed_todo_ids is None:
      completed_todo_ids = []

    for i, todo in enumerate(todos):
      deps_text = f" (depends on: {', '.join(map(str, todo.dependencies))})" if todo.dependencies else ""
      is_completed = todo.id in completed_todo_ids
      is_current = todo.id == current_todo_id

      if i == 0:
        # First todo on same line as ⎿
        if is_completed:
          self.console.print(f"  [white]⎿[/white]  [#8FDC8D]☒ {todo.task}{deps_text}[/#8FDC8D]")
        elif is_current:
          self.console.print(f"  [white]⎿[/white]  [bold #B7E0FF]⏺ {todo.task}{deps_text}[/bold #B7E0FF]")
        else:
          self.console.print(f"  [white]⎿[/white]  [white]☐ {todo.task}{deps_text}[/white]")
      else:
        # Subsequent todos aligned with first
        if is_completed:
          self.console.print(f"     [#8FDC8D]☒ {todo.task}{deps_text}[/#8FDC8D]")
        elif is_current:
          self.console.print(f"     [bold #B7E0FF]⏺ {todo.task}{deps_text}[/bold #B7E0FF]")
        else:
          self.console.print(f"     [white]☐ {todo.task}{deps_text}[/white]")
    self.console.print()  # Add spacing after todo plan

  def show_processing_todo(self, todo_id: int, task: str):
    self.show_step(f"Working on todo {todo_id}: {task}")
    self.console.print()  # Add spacing after step

  def show_todo_thinking(self, thinking: str):
    # Show truncated thinking process
    truncated = thinking[:200] + "..." if len(thinking) > 200 else thinking
    self.console.print(f"  [bright_white] {truncated}[/bright_white]")
    self.console.print()  # Add spacing after thinking

  def show_todo_completion(self, todo_id: int, completed: bool, next_steps: str = ""):
    if completed:
      self.show_step(f"Completed todo {todo_id}", is_final=True)
    else:
      self.show_step(f"Todo {todo_id} needs more work")
      if next_steps:
        self.console.print(f"  [bright_white]Next: {next_steps}[/bright_white]")
    self.console.print()  # Add spacing after completion

  def show_llm_retry(self, attempt: int, max_retries: int, error: str):
    self.console.print(f"  [bright_white]️ LLM request failed (attempt {attempt}/{max_retries}): {error[:50]}...[/bright_white]")
    self.console.print(f"  [bright_white] Retrying in {2 ** (attempt - 1)} seconds...[/bright_white]")
    self.console.print()  # Add spacing after retry message

  def show_llm_retry_success(self, final_attempt: int):
    self.console.print(f"  [bright_white]● LLM request succeeded on attempt {final_attempt}[/bright_white]")
    self.console.print()  # Add spacing after success

  def show_llm_retry_failed(self, max_retries: int, final_error: str):
    self.console.print(f"  [red]● LLM request failed after {max_retries} attempts[/red]")
    self.console.print(f"  [red]Final error: {final_error[:100]}...[/red]")
    self.console.print()  # Add spacing after failure

  def show_error(self, error: str):
    self.console.print()
    self.console.print(f"[red] Error: {error}[/red]")

  def show_partial_success(self, successful_edits: int, total_edits: int, error: str):
    self.console.print()
    self.console.print(f"[bright_white]⚠️ Applied {successful_edits}/{total_edits} edits before encountering error:[/bright_white]")
    self.console.print(f"[red]{error}[/red]")

  def show_rejection(self):
    self.console.print()
    self.console.print("[bright_white]Changes rejected[/bright_white]")

  def show_goodbye(self):
    self.console.print()
    self.console.print("[bright_white]Goodbye![/bright_white]")

  def ask_continue(self) -> bool:
    return True  # Always continue, no prompt needed

  def show_edit_validation_error(self, edit: FileEdit, error: str):
    self.console.print()
    self.console.print(f"[red] Validation failed for {edit.file_path}: {error}[/red]")

  def clear_screen(self):
    self.console.clear()

  def print_separator(self):
    self.console.print()
    self.console.print(Rule(style="dim"))

  def show_todo_update_header(self):
    """Show the 'Update Todos' header"""
    self.console.print()
    # Custom formatting for Update Todos header
    bullet = "⏺"
    self.console.print(f"[white]{bullet}[/white] [bold bright_white]Update Todos[/bold bright_white]")
    self._first_todo_in_update = True

  def show_todo_status(self, todo_id: int, task: str, completed: bool, is_current: bool = False):
    """Show individual todo status with new formatting"""
    if hasattr(self, "_first_todo_in_update") and self._first_todo_in_update:
      # First todo on same line as ⎿
      if completed:
        self.console.print(f"  [white]⎿[/white]  [#8FDC8D]☒ {task}[/#8FDC8D]")
      elif is_current:
        self.console.print(f"  [white]⎿[/white]  [bold #B7E0FF]⏺ {task}[/bold #B7E0FF]")
      else:
        self.console.print(f"  [white]⎿[/white]  [white]☐ {task}[/white]")
      self._first_todo_in_update = False
    else:
      # Subsequent todos aligned with first
      if completed:
        self.console.print(f"     [#8FDC8D]☒ {task}[/#8FDC8D]")
      elif is_current:
        self.console.print(f"     [bold #B7E0FF]⏺ {task}[/bold #B7E0FF]")
      else:
        self.console.print(f"     [white]☐ {task}[/white]")

  def show_todo_update_complete(self):
    """Add spacing after todo updates"""
    self.console.print()  # Add spacing after todo updates

  def show_command_execution(self, command: str):
    """Show that a command is being executed"""
    self.show_step("Bash")
    self.console.print(f"  [white]Running: {command}[/white]")

  def show_command_result(self, result):
    """Show the result of a command execution"""
    from .agent import CommandResult

    if not isinstance(result, CommandResult):
      return

    self.console.print()
    if result.success:
      self.console.print(f"[#60875F]●[/#60875F] [bright_white]Command completed (exit code: {result.exit_code})[/bright_white]")
    else:
      self.console.print(f"[red]●[/red] [bright_white]Command failed (exit code: {result.exit_code})[/bright_white]")

    if result.stdout.strip():
      self.console.print("  [white]Output:[/white]")
      # Truncate very long output
      stdout_display = result.stdout[:1000] + "..." if len(result.stdout) > 1000 else result.stdout
      for line in stdout_display.strip().split("\n"):
        self.console.print(f"    [white]{line}[/white]")

    if result.stderr.strip():
      # Show stderr with appropriate labeling based on command success
      if result.success:
        self.console.print("  [white]Output:[/white]")
        stderr_display = result.stderr[:500] + "..." if len(result.stderr) > 500 else result.stderr
        for line in stderr_display.strip().split("\n"):
          self.console.print(f"    [white]{line}[/white]")
      else:
        self.console.print("  [white]Error output:[/white]")
        stderr_display = result.stderr[:500] + "..." if len(result.stderr) > 500 else result.stderr
        for line in stderr_display.strip().split("\n"):
          self.console.print(f"    [red]{line}[/red]")

    self.console.print()  # Add spacing after command result

  def start_loading(self, message: str = "Thinking"):
    """Start animated loading indicator"""
    if self.loading_active:
      return

    self.loading_active = True

    def animate_loading():
      animation_count = 0
      start_time = time.time()
      while self.loading_active:
        # Animate bullet between circle, *, +
        bullets = ["○", "*", "+"]
        bullet = bullets[animation_count % 3]

        # Animate dots
        dots = "." * (animation_count % 4)
        spaces = " " * (3 - len(dots))

        # Calculate elapsed time
        elapsed_seconds = int(time.time() - start_time)
        time_display = f"({elapsed_seconds}s)"

        loading_text = f"[bold #EB999A]{bullet}[/bold #EB999A] [bold #EB999A]{message}{dots}{spaces}[/bold #EB999A] [dim white]{time_display}[/dim white]"

        if self.loading_live is None:
          self.loading_live = Live(loading_text, console=self.console, refresh_per_second=4)
          self.loading_live.start()
        else:
          self.loading_live.update(loading_text)

        time.sleep(0.25)
        animation_count += 1

    self.loading_task = threading.Thread(target=animate_loading, daemon=True)
    self.loading_task.start()

  def stop_loading(self):
    """Stop animated loading indicator"""
    if not self.loading_active:
      return

    self.loading_active = False

    if self.loading_live:
      self.loading_live.stop()
      self.loading_live = None

    if self.loading_task:
      self.loading_task.join(timeout=0.5)
      self.loading_task = None

  def _handle_init_command(self):
    """Handle the /init command to create aieng.toml file"""
    import os

    toml_path = "aieng.toml"

    if os.path.exists(toml_path):
      self.console.print(f"[#EB999A]● aieng.toml already exists[/#EB999A]")
      return

    # Create TOML file with configuration structure
    toml_content = """# AIENG Configuration File
# This file stores persistent settings for the AIENG tool

# API Configuration
api_base_url = "https://api.x.ai/v1"  # API base URL

# Model Configuration
model = "grok-4"  # Default model (grok-3 or grok-4)

# General Settings
auto_accept = false  # Auto-accept file edits without confirmation
"""

    try:
      with open(toml_path, "w") as f:
        f.write(toml_content)
      self.console.print(f"[#60875F]● Created aieng.toml[/#60875F]")
      self.console.print(f"[yellow]● Make sure API_KEY environment variable is set with your API key[/yellow]")
    except Exception as e:
      self.console.print(f"[red]● Error creating aieng.toml: {e}[/red]")

  def _handle_help_command(self):
    """Handle the /help command"""
    self.console.print()
    self.console.print("[bold bright_white]Available Commands:[/bold bright_white]")
    self.console.print()

    commands = [
      ("/init", "Create a aieng.toml file with configuration settings"),
      ("/model", "Switch between available AI models (grok-3, grok-4)"),
      ("/auto", "Toggle auto-accept edits on/off"),
      ("/help", "Show this help message"),
      ("/exit", "Exit the AIENG tool"),
      ("/clear", "Clear the screen and start fresh"),
    ]

    for cmd, description in commands:
      self.console.print(f"  [bright_white]{cmd:<16}[/bright_white] [white]{description}[/white]")

  def _handle_exit_command(self):
    """Handle the /exit command"""
    self.console.print()
    self.console.print("[bright_white]Goodbye![/bright_white]")
    import sys

    sys.exit(0)

  def _handle_clear_command(self):
    """Handle the /clear command"""
    self.clear_screen()

  def _handle_model_command(self):
    """Handle the /model command to switch between models"""
    self.console.print()
    self.console.print("[bold bright_white]Available Models:[/bold bright_white]")
    self.console.print()

    models = ["grok-3", "grok-4"]
    for i, model in enumerate(models, 1):
      self.console.print(f"  [bright_white]{i}. {model}[/bright_white]")

    self.console.print()

    # Get user choice
    while True:
      try:
        choice = Prompt.ask("Select model (1-2)", choices=["1", "2"])
        selected_model = models[int(choice) - 1]
        self.console.print(f"[#60875F]● Switched to {selected_model}[/#60875F]")
        return f"__MODEL_CHANGE__{selected_model}"  # Special return value for model change
      except (ValueError, IndexError):
        self.console.print("[red]Invalid choice. Please select 1 or 2.[/red]")

  def _handle_auto_command(self):
    """Handle the /auto command to toggle auto-accept edits"""
    self.console.print()
    current_state = "enabled" if self.auto_accept else "disabled"
    self.console.print(f"[bright_white]Auto-accept edits is currently: {current_state}[/bright_white]")
    self.console.print()

    # Show options
    self.console.print("[bright_white]1. Enable auto-accept[/bright_white]")
    self.console.print("[bright_white]2. Disable auto-accept[/bright_white]")
    self.console.print()

    # Get user choice
    while True:
      try:
        choice = Prompt.ask("Select option (1-2)", choices=["1", "2"])
        new_state = choice == "1"
        new_state_text = "enabled" if new_state else "disabled"

        if new_state != self.auto_accept:
          self.console.print(f"[#60875F]● Auto-accept edits {new_state_text}[/#60875F]")
          return f"__AUTO_TOGGLE__{new_state}"  # Special return value for auto-accept toggle
        else:
          self.console.print("[bright_white]Auto-accept setting unchanged[/bright_white]")
          return None
      except (ValueError, IndexError):
        self.console.print("[red]Invalid choice. Please select 1 or 2.[/red]")
