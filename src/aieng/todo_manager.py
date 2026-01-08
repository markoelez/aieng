"""TodoManager - Centralized todo state management inspired by Claude Code.

This module provides a TodoManager class that handles all todo-related state
management, including creating plans, updating statuses, and tracking progress.
"""

from typing import List, Callable, Optional

from .models import Todo, TodoPlan, TodoStatus


class TodoManager:
  """Manages todo state and provides methods for the agentic loop.

  This class follows Claude Code's pattern of maintaining a tight agentic loop
  where the agent creates a plan with todos and executes against them with
  proper state tracking.
  """

  def __init__(self, ui_callback: Optional[Callable] = None):
    """Initialize the TodoManager.

    Args:
      ui_callback: Optional callback for UI updates
    """
    self.todos: List[Todo] = []
    self.plan_summary: str = ""
    self.ui_callback = ui_callback
    self._current_todo_id: Optional[int] = None

  def set_plan(self, plan: TodoPlan) -> None:
    """Set the todo plan and initialize all todos as pending.

    Args:
      plan: The TodoPlan containing todos to track
    """
    self.plan_summary = plan.summary
    self.todos = []
    for todo in plan.todos:
      # Ensure all todos start as pending
      todo_copy = todo.model_copy()
      todo_copy.status = TodoStatus.PENDING
      self.todos.append(todo_copy)
    self._notify_ui("plan_set", {"summary": self.plan_summary, "todos": self.todos})

  def get_todo(self, todo_id: int) -> Optional[Todo]:
    """Get a todo by ID.

    Args:
      todo_id: The ID of the todo to retrieve

    Returns:
      The Todo if found, None otherwise
    """
    for todo in self.todos:
      if todo.id == todo_id:
        return todo
    return None

  def mark_in_progress(self, todo_id: int) -> None:
    """Mark a todo as in progress.

    Args:
      todo_id: The ID of the todo to mark
    """
    for todo in self.todos:
      if todo.id == todo_id:
        todo.status = TodoStatus.IN_PROGRESS
        self._current_todo_id = todo_id
        self._notify_ui("todo_in_progress", {"todo": todo})
        break

  def mark_completed(self, todo_id: int) -> None:
    """Mark a todo as completed.

    Args:
      todo_id: The ID of the todo to mark
    """
    for todo in self.todos:
      if todo.id == todo_id:
        todo.status = TodoStatus.COMPLETED
        if self._current_todo_id == todo_id:
          self._current_todo_id = None
        self._notify_ui("todo_completed", {"todo": todo})
        break

  def add_todo(
    self, task: str, reasoning: str = "", priority: str = "medium", active_form: str = "", dependencies: Optional[List[int]] = None
  ) -> Todo:
    """Add a new todo dynamically during execution.

    This allows the agent to add new todos as it discovers more work is needed.

    Args:
      task: The task description
      reasoning: Why this task is needed
      priority: Task priority (high/medium/low)
      active_form: Present continuous form for UI display
      dependencies: List of todo IDs this depends on

    Returns:
      The newly created Todo
    """
    # Generate new ID (max existing + 1)
    new_id = max([t.id for t in self.todos], default=0) + 1

    new_todo = Todo(
      id=new_id,
      task=task,
      active_form=active_form or f"{task}...",
      reasoning=reasoning,
      priority=priority,
      status=TodoStatus.PENDING,
      dependencies=dependencies or [],
    )

    self.todos.append(new_todo)
    self._notify_ui("todo_added", {"todo": new_todo})
    return new_todo

  def remove_todo(self, todo_id: int) -> bool:
    """Remove a todo from the list.

    Args:
      todo_id: The ID of the todo to remove

    Returns:
      True if removed, False if not found
    """
    for i, todo in enumerate(self.todos):
      if todo.id == todo_id:
        removed = self.todos.pop(i)
        self._notify_ui("todo_removed", {"todo": removed})
        return True
    return False

  def get_ready_todos(self) -> List[Todo]:
    """Get todos that are ready to be worked on.

    A todo is ready if:
    - It is pending
    - All its dependencies are completed

    Returns:
      List of todos ready for processing
    """
    completed_ids = {t.id for t in self.todos if t.is_completed()}
    ready = []

    for todo in self.todos:
      if todo.is_pending():
        # Check if all dependencies are completed
        deps_satisfied = all(dep_id in completed_ids for dep_id in todo.dependencies)
        if deps_satisfied:
          ready.append(todo)

    return ready

  def get_next_todo(self) -> Optional[Todo]:
    """Get the next todo to work on.

    Returns the highest priority ready todo, or None if no todos are ready.

    Returns:
      The next Todo to process, or None
    """
    ready = self.get_ready_todos()
    if not ready:
      return None

    # Sort by priority (high > medium > low)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    ready.sort(key=lambda t: (priority_order.get(t.priority, 1), t.id))

    return ready[0]

  def get_current_todo(self) -> Optional[Todo]:
    """Get the currently in-progress todo.

    Returns:
      The current Todo if one is in progress, None otherwise
    """
    if self._current_todo_id is None:
      return None
    return self.get_todo(self._current_todo_id)

  def get_pending_todos(self) -> List[Todo]:
    """Get all pending todos.

    Returns:
      List of pending todos
    """
    return [t for t in self.todos if t.is_pending()]

  def get_completed_todos(self) -> List[Todo]:
    """Get all completed todos.

    Returns:
      List of completed todos
    """
    return [t for t in self.todos if t.is_completed()]

  def is_all_completed(self) -> bool:
    """Check if all todos are completed.

    Returns:
      True if all todos are completed
    """
    return all(t.is_completed() for t in self.todos)

  def has_remaining_work(self) -> bool:
    """Check if there is remaining work.

    Returns:
      True if there are pending or in-progress todos
    """
    return any(not t.is_completed() for t in self.todos)

  def get_progress(self) -> tuple[int, int]:
    """Get the current progress.

    Returns:
      Tuple of (completed_count, total_count)
    """
    completed = len(self.get_completed_todos())
    total = len(self.todos)
    return (completed, total)

  def get_state_snapshot(self) -> dict:
    """Get a snapshot of the current state for UI display.

    Returns:
      Dictionary containing current state information
    """
    completed, total = self.get_progress()
    current = self.get_current_todo()

    return {
      "summary": self.plan_summary,
      "todos": self.todos,
      "current_todo": current,
      "completed_count": completed,
      "total_count": total,
      "progress_percent": (completed / total * 100) if total > 0 else 0,
      "is_complete": self.is_all_completed(),
    }

  def _notify_ui(self, event: str, data: dict) -> None:
    """Notify the UI about state changes.

    Args:
      event: The event type
      data: Event data
    """
    if self.ui_callback:
      self.ui_callback(event, data)
