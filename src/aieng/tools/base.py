"""Base classes for tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class Tool(ABC):
    """Base class for all tools."""
    
    def __init__(self, ui_callback: Optional[callable] = None):
        self.ui_callback = ui_callback
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def _notify_ui(self, event: str, *args, **kwargs) -> None:
        """Notify the UI of an event."""
        if self.ui_callback:
            self.ui_callback(event, *args, **kwargs)