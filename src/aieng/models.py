"""Shared data models for the AI coding agent."""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass

from pydantic import BaseModel, field_validator


class TodoStatus(str, Enum):
  """Status of a todo item, following Claude Code's pattern."""

  PENDING = "pending"
  IN_PROGRESS = "in_progress"
  COMPLETED = "completed"


@dataclass
class FileEdit:
  """Represents a file edit operation."""

  file_path: str
  old_content: str
  new_content: str
  description: str


@dataclass
class SearchResult:
  """Represents a search operation result."""

  query: str
  command: str
  results: str
  description: str


class LLMResponse(BaseModel):
  """Response from LLM for processing requests."""

  summary: str
  commands: List[Dict[str, str]] = []
  edits: List[Dict[str, str]]


class Todo(BaseModel):
  """Represents a todo item with state management like Claude Code."""

  id: int
  task: str  # The imperative form (e.g., "Run tests")
  active_form: str = ""  # The present continuous form (e.g., "Running tests")
  reasoning: str
  priority: str  # "high", "medium", "low"
  status: TodoStatus = TodoStatus.PENDING
  dependencies: List[int] = []  # IDs of todos this depends on

  @field_validator("active_form", mode="before")
  @classmethod
  def set_active_form(cls, v, info):
    """Auto-generate active_form from task if not provided."""
    if not v and info.data.get("task"):
      task = info.data["task"]
      # Simple transformation: if starts with a verb, convert to -ing form
      return f"{task}..."
    return v or ""

  def is_pending(self) -> bool:
    return self.status == TodoStatus.PENDING

  def is_in_progress(self) -> bool:
    return self.status == TodoStatus.IN_PROGRESS

  def is_completed(self) -> bool:
    return self.status == TodoStatus.COMPLETED


class TodoPlan(BaseModel):
  """Represents a plan consisting of multiple todos."""

  summary: str
  todos: List[Todo]


class CommandResult(BaseModel):
  """Result of a command execution."""

  command: str
  stdout: str
  stderr: str
  exit_code: int
  success: bool


class SelfReflection(BaseModel):
  """Self-reflection analysis for planning next actions."""

  current_state: str  # Analysis of current progress
  next_action_plan: str  # Detailed plan for next actions
  action_type: str  # "edits", "commands", "searches", or "mixed"
  confidence_level: str  # "high", "medium", "low"


class TodoResult(BaseModel):
  """Result of processing a todo."""

  thinking: str
  commands: List[Dict[str, str]] = []
  searches: List[Dict[str, str]] = []
  edits: List[Dict[str, str]] = []
  completed: bool
  next_steps: Optional[str] = ""

  @field_validator("next_steps")
  @classmethod
  def validate_next_steps(cls, v):
    if v is None:
      return ""
    return str(v)

  @field_validator("commands")
  @classmethod
  def validate_commands(cls, v):
    if v is None:
      return []
    if not isinstance(v, list):
      return []
    validated_commands = []
    for cmd in v:
      if isinstance(cmd, dict):
        command_dict = {"command": str(cmd.get("command", "")), "description": str(cmd.get("description", ""))}
        validated_commands.append(command_dict)
    return validated_commands

  @field_validator("searches")
  @classmethod
  def validate_searches(cls, v):
    if v is None:
      return []
    if not isinstance(v, list):
      return []
    validated_searches = []
    for search in v:
      if isinstance(search, dict):
        search_dict = {
          "query": str(search.get("query", "")),
          "command": str(search.get("command", "")),
          "description": str(search.get("description", "")),
        }
        validated_searches.append(search_dict)
    return validated_searches

  @field_validator("edits")
  @classmethod
  def validate_edits(cls, v):
    if v is None:
      return []
    if not isinstance(v, list):
      return []
    validated_edits = []
    for edit in v:
      if isinstance(edit, dict):
        edit_dict = {
          "file_path": str(edit.get("file_path", "")),
          "old_content": str(edit.get("old_content", "")),
          "new_content": str(edit.get("new_content", "")),
          "description": str(edit.get("description", "")),
        }
        validated_edits.append(edit_dict)
    return validated_edits
