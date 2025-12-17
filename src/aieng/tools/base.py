"""Base classes for tools."""

from abc import ABC
from typing import Any, Callable, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
  """Result from a tool execution."""

  success: bool
  data: Any = None
  error: Optional[str] = None


class Tool(ABC):
  """Base class for all tools."""

  def __init__(self, ui_callback: Optional[Callable[..., None]] = None):
    self.ui_callback = ui_callback

  async def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
    """Execute the tool with given parameters."""
    raise NotImplementedError("Subclasses must implement execute()")

  def _notify_ui(self, event: str, *args, **kwargs) -> None:
    """Notify the UI of an event."""
    if self.ui_callback:
      self.ui_callback(event, *args, **kwargs)
