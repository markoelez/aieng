"""Tests for terminal UI output formatting and spacing."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from aieng.ui import TerminalUI
from aieng.models import Todo, TodoStatus, SelfReflection


class TestUISpacing:
  """Tests to ensure consistent spacing between task blocks."""

  @pytest.fixture
  def ui(self) -> TerminalUI:
    """Create a TerminalUI instance with a captured console."""
    ui = TerminalUI()
    # Replace console with one that captures output
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=80)
    return ui

  def get_output(self, ui: TerminalUI) -> str:
    """Get the captured output from the UI console."""
    file = ui.console.file
    if isinstance(file, io.StringIO):
      return file.getvalue()
    return ""

  def count_blank_lines(self, output: str) -> int:
    """Count consecutive blank lines in output."""
    lines = output.split("\n")
    blank_count = 0
    max_consecutive = 0
    current_consecutive = 0

    for line in lines:
      if line.strip() == "":
        current_consecutive += 1
        blank_count += 1
      else:
        max_consecutive = max(max_consecutive, current_consecutive)
        current_consecutive = 0

    return max_consecutive

  def test_add_spacing_adds_one_blank_line(self, ui: TerminalUI):
    """Test that _add_spacing adds exactly one blank line."""
    ui._add_spacing()
    output = self.get_output(ui)
    # Should have exactly one newline (which appears as empty line)
    assert output == "\n"

  def test_multiple_add_spacing_calls(self, ui: TerminalUI):
    """Test that multiple _add_spacing calls each add one line."""
    ui._add_spacing()
    ui._add_spacing()
    ui._add_spacing()
    output = self.get_output(ui)
    # Should have exactly 3 newlines
    assert output == "\n\n\n"

  def test_show_step_includes_spacing(self, ui: TerminalUI):
    """Test that show_step adds proper spacing."""
    ui.show_step("Test step message")
    output = self.get_output(ui)
    # Should start with a blank line and contain the message
    assert output.startswith("\n")
    assert "Test step message" in output

  def test_show_error_includes_spacing(self, ui: TerminalUI):
    """Test that show_error adds proper spacing."""
    ui.show_error("Test error message")
    output = self.get_output(ui)
    # Should start with a blank line and contain the error
    assert output.startswith("\n")
    assert "Test error message" in output

  def test_show_processing_todo_includes_spacing(self, ui: TerminalUI):
    """Test that show_processing_todo adds proper spacing."""
    ui.show_processing_todo(1, "Test task")
    output = self.get_output(ui)
    # Should start with a blank line
    assert output.startswith("\n")
    assert "Test task" in output

  def test_show_todo_completion_includes_spacing(self, ui: TerminalUI):
    """Test that show_todo_completion adds proper spacing."""
    ui.show_todo_completion(1, True)
    output = self.get_output(ui)
    # Should start with a blank line
    assert output.startswith("\n")
    assert "completed" in output.lower() or "✓" in output or "✔" in output

  def test_show_self_reflection_includes_spacing(self, ui: TerminalUI):
    """Test that show_self_reflection adds proper spacing."""
    reflection = SelfReflection(
      current_state="Test state analysis",
      next_action_plan="Plan for next actions",
      action_type="edits",
      confidence_level="high",
    )
    ui.show_self_reflection(reflection)
    output = self.get_output(ui)
    # Should start with a blank line
    assert output.startswith("\n")

  def test_show_diff_header_includes_spacing(self, ui: TerminalUI):
    """Test that show_diff_header adds proper spacing."""
    ui.show_diff_header("test.py", "Test description", False)
    output = self.get_output(ui)
    # Should start with a blank line
    assert output.startswith("\n")
    assert "test.py" in output

  def test_show_command_execution_includes_spacing(self, ui: TerminalUI):
    """Test that show_command_execution adds proper spacing."""
    ui.show_command_execution("ls -la")
    output = self.get_output(ui)
    # Should start with a blank line
    assert output.startswith("\n")
    assert "ls -la" in output


class TestUITodoDisplay:
  """Tests for todo list display functionality."""

  @pytest.fixture
  def ui(self) -> TerminalUI:
    """Create a TerminalUI instance with a captured console."""
    ui = TerminalUI()
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=80)
    return ui

  def get_output(self, ui: TerminalUI) -> str:
    """Get the captured output from the UI console."""
    file = ui.console.file
    if isinstance(file, io.StringIO):
      return file.getvalue()
    return ""

  def test_show_todo_list_displays_all_todos(self, ui: TerminalUI):
    """Test that show_todo_list displays all provided todos."""
    todos = [
      Todo(id=1, task="First task", active_form="Working on first task...", reasoning="Needed", priority="high", status=TodoStatus.PENDING),
      Todo(
        id=2,
        task="Second task",
        active_form="Working on second task...",
        reasoning="Also needed",
        priority="medium",
        status=TodoStatus.PENDING,
      ),
    ]
    ui.show_todo_list(todos, current_todo_id=None)
    output = self.get_output(ui)
    assert "First task" in output
    assert "Second task" in output

  def test_show_todo_list_shows_status_indicators(self, ui: TerminalUI):
    """Test that show_todo_list shows different status indicators."""
    todos = [
      Todo(id=1, task="Completed task", active_form="Completing task...", reasoning="Done", priority="high", status=TodoStatus.COMPLETED),
      Todo(
        id=2,
        task="In progress task",
        active_form="Working on progress task...",
        reasoning="Working",
        priority="medium",
        status=TodoStatus.IN_PROGRESS,
      ),
      Todo(id=3, task="Pending task", active_form="Starting pending task...", reasoning="Todo", priority="low", status=TodoStatus.PENDING),
    ]
    ui.show_todo_list(todos, current_todo_id=2)
    output = self.get_output(ui)
    # Completed and pending todos show the task, in-progress shows active_form
    assert "Completed task" in output
    assert "Working on progress task" in output  # active_form for in-progress (ellipsis may be in separate span)
    assert "Pending task" in output

  def test_show_todo_added(self, ui: TerminalUI):
    """Test that show_todo_added displays the new todo."""
    todo = Todo(
      id=1,
      task="New task",
      active_form="Adding new task...",
      reasoning="Discovered during work",
      priority="high",
      status=TodoStatus.PENDING,
    )
    ui.show_todo_added(todo)
    output = self.get_output(ui)
    assert "New task" in output


class TestUILoadingIndicator:
  """Tests for loading indicator functionality."""

  @pytest.fixture
  def ui(self) -> TerminalUI:
    """Create a TerminalUI instance."""
    ui = TerminalUI()
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=80)
    return ui

  def test_start_loading_sets_active_flag(self, ui: TerminalUI):
    """Test that start_loading sets the loading_active flag."""
    assert ui.loading_active is False
    ui.start_loading("Testing")
    assert ui.loading_active is True
    ui.stop_loading()

  def test_stop_loading_clears_active_flag(self, ui: TerminalUI):
    """Test that stop_loading clears the loading_active flag."""
    ui.start_loading("Testing")
    assert ui.loading_active is True
    ui.stop_loading()
    assert ui.loading_active is False

  def test_stop_loading_when_not_active_does_nothing(self, ui: TerminalUI):
    """Test that stop_loading when not active doesn't raise errors."""
    assert ui.loading_active is False
    ui.stop_loading()  # Should not raise
    assert ui.loading_active is False


class TestUINoDoubleSpacing:
  """Tests to ensure no double blank lines appear in output sequences."""

  @pytest.fixture
  def ui(self) -> TerminalUI:
    """Create a TerminalUI instance with a captured console."""
    ui = TerminalUI()
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=80)
    return ui

  def get_output(self, ui: TerminalUI) -> str:
    """Get the captured output from the UI console."""
    file = ui.console.file
    if isinstance(file, io.StringIO):
      return file.getvalue()
    return ""

  def has_triple_or_more_newlines(self, output: str) -> bool:
    """Check if output contains 3+ consecutive newlines (2+ blank lines)."""
    return "\n\n\n" in output

  def test_step_sequence_no_double_spacing(self, ui: TerminalUI):
    """Test that a sequence of steps doesn't produce double blank lines."""
    ui.show_step("Step 1")
    ui.show_step("Step 2")
    ui.show_step("Step 3")
    output = self.get_output(ui)
    # Should not have 3+ consecutive newlines (which would be 2+ blank lines)
    assert not self.has_triple_or_more_newlines(output), f"Found triple newlines in output: {repr(output)}"

  def test_error_after_step_no_double_spacing(self, ui: TerminalUI):
    """Test that error after step doesn't produce double blank lines."""
    ui.show_step("Step 1")
    ui.show_error("Error message")
    output = self.get_output(ui)
    assert not self.has_triple_or_more_newlines(output), f"Found triple newlines in output: {repr(output)}"

  def test_diff_header_sequence_no_double_spacing(self, ui: TerminalUI):
    """Test that diff headers don't produce double blank lines."""
    ui.show_diff_header("file1.py", "First change", False)
    ui.show_diff_header("file2.py", "Second change", False)
    output = self.get_output(ui)
    assert not self.has_triple_or_more_newlines(output), f"Found triple newlines in output: {repr(output)}"
