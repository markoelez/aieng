import sys
import time
import threading
from typing import List, Optional

from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt
from rich.console import Console

from .config import DEFAULT_MODEL, API_KEY_ENV_VAR, SUPPORTED_MODELS, DEFAULT_API_BASE_URL
from .models import FileEdit, TodoStatus, SelfReflection


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

  def _add_spacing(self):
    """Add a blank line for consistent spacing between task blocks."""
    self.console.print()

  def set_auto_accept(self, enabled: bool):
    """Set the auto-accept status for UI display"""
    self.auto_accept = enabled

  def _get_cursor_offset(self):
    """Get the number of lines to account for auto-accept indicator"""
    return 1 if self.auto_accept else 0

  def _show_command_menu(self):
    """Show the command menu under the input box"""
    model_list = ", ".join(SUPPORTED_MODELS)
    commands = [
      ("/init", "Create a aieng.toml file with configuration settings"),
      ("/model", f"Switch between available GPT Codex models ({model_list})"),
      ("/auto", "Toggle auto-accept edits on/off"),
      ("/help", "Show help and available commands"),
      ("/exit", "Exit the AIENG tool"),
      ("/clear", "Clear the screen and start fresh"),
    ]

    # Use Rich console for proper formatting
    for cmd, description in commands:
      self.console.print(f"  [bright_white]{cmd:<16}[/bright_white] [white]{description}[/white]")
    self.commands_visible = True

  def get_user_request(self) -> Optional[str]:
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

            # Return user input - each UI method handles its own spacing
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
    """Show a step in Claude Code style. Adds blank line before."""
    self._add_spacing()
    color = "bright_green" if is_final else "bright_white"
    self.console.print(f"[{color}]⏺[/{color}] [bright_white]{step_text}[/bright_white]")

  def show_analyzing_files(self, file_contexts: List[dict]):
    if not file_contexts:
      return

    self._add_spacing()
    self.console.print("[bright_white]⏺[/bright_white] [bright_white]Analyzing Files[/bright_white]")
    for ctx in file_contexts:
      self.console.print(f"  [bright_white]• {ctx['path']}[/bright_white]")

  def show_reading_file(self, file_path: str, lines_read: int = 0):
    """Show when a file is being read in Claude Code style"""
    self._add_spacing()
    self.console.print(
      f"[bright_white]⏺[/bright_white] [bold bright_white]Read[/bold bright_white]([bright_cyan]{file_path}[/bright_cyan])"
    )
    if lines_read > 0:
      self.console.print(f"  [bright_white]⎿[/bright_white]  [white]Read {lines_read} line{'s' if lines_read != 1 else ''}[/white]")

  def show_generating_response(self):
    self.show_step("Generating Response")

  def show_generating_edits(self, todo_id: str):
    """Show when edits are being generated for a todo"""
    self.show_step(f"Generating edits for todo {todo_id}")

  def show_search_header(self, query: str, search_description: str):
    """Show search in Claude Code style"""
    self._add_spacing()
    self.console.print(
      f"[bright_white]⏺[/bright_white] [bold bright_white]Search[/bold bright_white]([bright_magenta]{query}[/bright_magenta])"
    )
    self.console.print(f"  [bright_white]⎿[/bright_white]  [white]{search_description}[/white]")

  def show_search_content(self, command: str, results: str):
    """Show the actual search command and results"""
    if not results.strip():
      return

    # Show the command that was executed
    self.console.print(f"       [bright_yellow]$ {command}[/bright_yellow]")

    # Show search results with proper formatting
    lines = results.split("\n")
    for line in lines:
      if line.strip():
        self.console.print(f"         [bright_white]{line}[/bright_white]")

  def show_diff_header(
    self, file_path: str, edit_description: str, is_new_file: bool = False, added_lines: int = 0, removed_lines: int = 0
  ):
    """Show diff header in Claude Code style"""
    self._add_spacing()
    operation = "Write" if is_new_file else "Update"
    self.console.print(
      f"[bright_white]⏺[/bright_white] [bold bright_white]{operation}[/bold bright_white]([bright_cyan]{file_path}[/bright_cyan])"
    )

    if added_lines > 0 or removed_lines > 0:
      parts = []
      if added_lines > 0:
        parts.append(f"[bright_green]Added {added_lines} line{'s' if added_lines != 1 else ''}[/bright_green]")
      if removed_lines > 0:
        parts.append(f"[bright_red]removed {removed_lines} line{'s' if removed_lines != 1 else ''}[/bright_red]")
      self.console.print(f"  [bright_white]⎿[/bright_white]  {', '.join(parts)}")
    elif edit_description:
      self.console.print(f"  [bright_white]⎿[/bright_white]  [white]{edit_description}[/white]")

  def show_diff_content(self, diff_text: str):
    """Show the actual diff content in Claude Code style"""
    if not diff_text.strip():
      return

    import re

    lines = diff_text.split("\n")
    old_line_num = None
    new_line_num = None

    # Check for line number information
    has_line_numbers = any(line.startswith("@@") for line in lines)

    if not has_line_numbers:
      new_line_num = 1
      old_line_num = 1

    for line in lines:
      if line.startswith("@@"):
        match = re.search(r"@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)(?:,\d+)?\s*@@", line)
        if match:
          old_line_num = int(match.group(1))
          new_line_num = int(match.group(2))
        continue
      elif line.startswith("+++") or line.startswith("---"):
        continue
      elif line.startswith("+") and not line.startswith("+++"):
        # Added line - bright green
        line_content = line[1:] if len(line) > 1 else ""
        self.console.print(
          f"      [white]{new_line_num:>4}[/white] [bright_green]+[/bright_green] [bright_green]{line_content}[/bright_green]",
          overflow="ellipsis",
          no_wrap=True,
        )
        if new_line_num is not None:
          new_line_num += 1
      elif line.startswith("-") and not line.startswith("---"):
        # Removed line - bright red
        line_content = line[1:] if len(line) > 1 else ""
        self.console.print(
          f"      [white]{old_line_num:>4}[/white] [bright_red]-[/bright_red] [bright_red]{line_content}[/bright_red]",
          overflow="ellipsis",
          no_wrap=True,
        )
        if old_line_num is not None:
          old_line_num += 1
      elif line.startswith(" "):
        # Context line - regular white
        line_content = line[1:] if len(line) > 1 else ""
        self.console.print(
          f"      [white]{new_line_num:>4}[/white]   [white]{line_content}[/white]",
          overflow="ellipsis",
          no_wrap=True,
        )
        if new_line_num is not None:
          new_line_num += 1
        if old_line_num is not None:
          old_line_num += 1
      elif line.strip():
        self.console.print(f"             [white]{line}[/white]")

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
    """Show summary in GPT Codex style"""
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

  def confirm_single_file_change(self, file_path: str, auto_accept: bool = False) -> tuple[bool, bool, bool]:
    """
    Confirm changes for a single file.
    Returns (should_apply, continue_with_remaining, auto_accept_enabled)
    """
    self.console.print()
    if auto_accept:
      self.console.print(f"[bright_white]Auto-accepting changes to {file_path}[/bright_white]")
      return (True, True, False)  # Apply changes, continue, no change to auto-accept

    self.console.print(f"[bright_white]Apply changes to {file_path}?[/bright_white]")
    self.console.print("[bright_white]1. Yes, apply this file[/bright_white]")
    self.console.print("[bright_white]2. No, skip this file[/bright_white]")
    self.console.print("[bright_white]3. No, skip all remaining files[/bright_white]")
    choice = Prompt.ask("Enter your choice (1-3)", choices=["1", "2", "3"], default="2")

    if choice == "1":
      # Only ask about auto-accept on the first file approval
      self.console.print("[bright_white]Enable auto-accept for remaining files?[/bright_white]")
      self.console.print("[bright_white]1. Yes, auto-accept remaining[/bright_white]")
      self.console.print("[bright_white]2. No, ask for each file[/bright_white]")
      auto_choice = Prompt.ask("Enter your choice (1-2)", choices=["1", "2"], default="2")
      auto_accept_enabled = auto_choice == "1"
      return (True, True, auto_accept_enabled)
    elif choice == "2":
      return (False, True, False)  # Skip this file, continue with others
    else:  # choice == "3"
      return (False, False, False)  # Skip all remaining files

  def show_applying_changes(self):
    self.show_step("Applying Changes")

  def show_success(self, num_edits: int):
    self.show_step(f"Successfully applied {num_edits} edit(s)", is_final=True)

  def show_generating_summary(self):
    self.show_step("Generating Summary")

  def show_edit_summary(self, summary: str):
    self.show_step("Summary", is_final=True)
    # Display the bulleted list of edits
    for line in summary.split("\n"):
      if line.strip():
        self.console.print(f"  [white]{line}[/white]")

  def show_planning(self):
    self.show_step("Planning")

  def show_todo_plan(self, plan_summary: str, todos, current_todo_id=None, completed_todo_ids=None):
    self._add_spacing()
    self.console.print("[bright_white]⏺[/bright_white] [bold bright_white]Update Todos[/bold bright_white]")

    if completed_todo_ids is None:
      completed_todo_ids = []

    for i, todo in enumerate(todos):
      deps_text = f" (depends on: {', '.join(map(str, todo.dependencies))})" if todo.dependencies else ""
      is_completed = todo.id in completed_todo_ids
      is_current = todo.id == current_todo_id

      if is_completed:
        icon, style = "☒", "#8FDC8D"
      elif is_current:
        icon, style = "⏺", "bold #B7E0FF"
      else:
        icon, style = "☐", "white"

      prefix = "  [white]⎿[/white]  " if i == 0 else "     "
      self.console.print(f"{prefix}[{style}]{icon} {todo.task}{deps_text}[/{style}]")

  def show_processing_todo(self, todo_id: int, task: str):
    """Show which todo is being processed"""
    self._add_spacing()
    self.console.print(
      f"[bright_cyan]⏺[/bright_cyan] [bold bright_white]Working on:[/bold bright_white] [bright_white]{task}[/bright_white]"
    )

  def show_self_reflection(self, reflection: SelfReflection):
    """Show self-reflection in Claude Code style"""
    self._add_spacing()
    self.console.print(f"[bright_white]⏺[/bright_white] [bright_white]{reflection.current_state}[/bright_white]")

  def show_todo_thinking(self, thinking: str):
    """Show thinking process - minimal display"""
    # Only show if there's substantial thinking
    if thinking and len(thinking.strip()) > 20:
      truncated = thinking[:150] + "..." if len(thinking) > 150 else thinking
      self.console.print(f"  [white]{truncated}[/white]")

  def show_todo_completion(self, todo_id: int, completed: bool, next_steps: str = ""):
    """Show todo completion status"""
    self._add_spacing()
    bullet = "⏺"
    color = "bright_green" if completed else "bright_red"
    status = "Completed" if completed else "Incomplete"
    self.console.print(f"[{color}]{bullet}[/{color}] [{color}]{status}[/{color}]")
    if not completed and next_steps:
      self.console.print(f"  [bright_white]⎿[/bright_white]  [white]Next: {next_steps}[/white]")

  def show_llm_retry(self, attempt: int, max_retries: int, error: str):
    self.console.print(f"  [bright_white]️ LLM request failed (attempt {attempt}/{max_retries}): {error[:50]}...[/bright_white]")
    self.console.print(f"  [bright_white] Retrying in {2 ** (attempt - 1)} seconds...[/bright_white]")

  def show_llm_retry_success(self, final_attempt: int):
    self.console.print(f"  [bright_white]● LLM request succeeded on attempt {final_attempt}[/bright_white]")

  def show_llm_retry_failed(self, max_retries: int, final_error: str):
    self.console.print(f"  [red]● LLM request failed after {max_retries} attempts[/red]")
    self.console.print(f"  [red]Final error: {final_error[:100]}...[/red]")

  def show_error(self, error: str):
    """Show error in Claude Code style"""
    self._add_spacing()
    self.console.print(f"[bright_red]⏺[/bright_red] [bright_red]Error: {error}[/bright_red]")

  def show_partial_success(self, successful_edits: int, total_edits: int, error: str):
    self._add_spacing()
    self.console.print(f"[bright_white]⚠️ Applied {successful_edits}/{total_edits} edits before encountering error:[/bright_white]")
    self.console.print(f"[red]{error}[/red]")

  def show_rejection(self):
    self._add_spacing()
    self.console.print("[bright_white]Changes rejected[/bright_white]")

  def show_goodbye(self):
    self._add_spacing()
    self.console.print("[bright_white]Goodbye![/bright_white]")

  def ask_continue(self) -> bool:
    return True  # Always continue, no prompt needed

  def show_edit_validation_error(self, edit: FileEdit, error: str):
    self._add_spacing()
    self.console.print(f"[red] Validation failed for {edit.file_path}: {error}[/red]")

  def clear_screen(self):
    self.console.clear()

  def show_todo_list(self, todos: list, current_todo_id: Optional[int] = None):
    """Show the todo list with status indicators like Claude Code."""
    self._add_spacing()
    self.console.print("[bright_white]⏺[/bright_white] [bold bright_white]Todo List[/bold bright_white]")

    for i, todo in enumerate(todos):
      is_in_progress = todo.status == TodoStatus.IN_PROGRESS or todo.id == current_todo_id

      if todo.status == TodoStatus.COMPLETED:
        status_icon, color = "☒", "bright_green"
      elif is_in_progress:
        status_icon, color = "⏺", "bright_cyan"
      else:
        status_icon, color = "☐", "bright_white"

      deps_text = f" [dim](depends on: {', '.join(map(str, todo.dependencies))})[/dim]" if todo.dependencies else ""
      display_text = (todo.active_form or todo.task) if is_in_progress else todo.task
      prefix = "  [bright_white]⎿[/bright_white]  " if i == 0 else "     "

      self.console.print(f"{prefix}[{color}]{status_icon} {display_text}[/{color}]{deps_text}")

  def show_todo_added(self, todo):
    """Show when a new todo is added dynamically.

    Args:
      todo: The newly added Todo object
    """
    self._add_spacing()
    self.console.print(f"[bright_cyan]+ Added new todo: {todo.task}[/bright_cyan]")

  def show_command_execution(self, command: str):
    """Show command execution in Claude Code style"""
    self._add_spacing()
    self.console.print(
      f"[bright_white]⏺[/bright_white] [bold bright_white]Bash[/bold bright_white]([bright_yellow]{command}[/bright_yellow])"
    )

  def show_command_result(self, result):
    """Show command result in Claude Code style"""
    from .agent import CommandResult

    if not isinstance(result, CommandResult):
      return

    # Combine stdout and stderr for display
    output = ""
    if result.stdout.strip():
      output = result.stdout.strip()
    if result.stderr.strip():
      if output:
        output += "\n"
      output += result.stderr.strip()

    # Show output with ⎿ symbol
    if not result.success:
      # Error state - show error message first
      self.console.print(f"  [bright_white]⎿[/bright_white]  [bright_red]Error: Exit code {result.exit_code}[/bright_red]")
      if output:
        output_display = output[:1500] + "..." if len(output) > 1500 else output
        lines = output_display.split("\n")
        for line in lines:
          self.console.print(f"     [white]{line}[/white]")
    elif output:
      # Success with output
      output_display = output[:1500] + "..." if len(output) > 1500 else output
      lines = output_display.split("\n")
      if lines:
        self.console.print(f"  [bright_white]⎿[/bright_white]  [bright_white]{lines[0]}[/bright_white]")
        for line in lines[1:]:
          self.console.print(f"     [bright_white]{line}[/bright_white]")
    else:
      # Success with no output
      self.console.print(f"  [bright_white]⎿[/bright_white]  [white](no output)[/white]")

  def start_loading(self, message: str = "Thinking"):
    """Start animated loading indicator that disappears when stopped."""
    if self.loading_active:
      return

    self._add_spacing()
    self.loading_active = True

    def animate_loading():
      animation_count = 0
      start_time = time.time()
      while self.loading_active:
        # Animate bullet
        bullets = ["○", "◐", "◑", "●"]
        bullet = bullets[animation_count % 4]

        # Animate dots
        dots = "." * ((animation_count % 3) + 1)
        spaces = " " * (3 - len(dots))

        # Calculate elapsed time
        elapsed_seconds = int(time.time() - start_time)
        time_display = f"({elapsed_seconds}s)"

        loading_text = f"[dim white]{bullet} {message}{dots}{spaces} {time_display}[/dim white]"

        if self.loading_live is None:
          # transient=True makes the loading indicator disappear when stopped
          self.loading_live = Live(loading_text, console=self.console, refresh_per_second=4, transient=True)
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
    toml_content = f"""# AIENG Configuration File
# This file stores persistent settings for the AIENG tool

# API Configuration
api_base_url = "{DEFAULT_API_BASE_URL}"  # API base URL

# Model Configuration
model = "{DEFAULT_MODEL}"  # Default GPT Codex model

# General Settings
auto_accept = false  # Auto-accept file edits without confirmation
"""

    try:
      with open(toml_path, "w") as f:
        f.write(toml_content)
      self.console.print(f"[#60875F]● Created aieng.toml[/#60875F]")
      self.console.print(f"[yellow]● Set the {API_KEY_ENV_VAR} environment variable with your API key[/yellow]")
    except Exception as e:
      self.console.print(f"[red]● Error creating aieng.toml: {e}[/red]")

  def _handle_help_command(self):
    """Handle the /help command"""
    self.console.print()
    self.console.print("[bold bright_white]Available Commands:[/bold bright_white]")
    self.console.print()

    model_list = ", ".join(SUPPORTED_MODELS)
    commands = [
      ("/init", "Create a aieng.toml file with configuration settings"),
      ("/model", f"Switch between available GPT Codex models ({model_list})"),
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

    for i, model in enumerate(SUPPORTED_MODELS, 1):
      self.console.print(f"  [bright_white]{i}. {model}[/bright_white]")

    self.console.print()

    # Get user choice
    while True:
      try:
        choices = [str(i) for i in range(1, len(SUPPORTED_MODELS) + 1)]
        choice = Prompt.ask(f"Select model (1-{len(SUPPORTED_MODELS)})", choices=choices)
        selected_model = SUPPORTED_MODELS[int(choice) - 1]
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
