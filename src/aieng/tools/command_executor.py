"""Command execution tool."""

import asyncio
import os
from typing import Optional

from .base import Tool, ToolResult
from ..models import CommandResult


class CommandExecutor(Tool):
    """Tool for executing shell commands."""
    
    def __init__(self, project_root: str = ".", ui_callback: Optional[callable] = None):
        super().__init__(ui_callback)
        self.project_root = os.path.abspath(project_root)
    
    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        """Execute a shell command in the project directory."""
        try:
            self._notify_ui("show_command_execution", command)
            
            # Run command in project directory
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                stdout_text = stdout.decode('utf-8') if stdout else ""
                stderr_text = stderr.decode('utf-8') if stderr else ""
                exit_code = process.returncode
                
                result = CommandResult(
                    command=command,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    exit_code=exit_code,
                    success=exit_code == 0
                )
                
                self._notify_ui("show_command_result", result)
                return ToolResult(success=True, data=result)
                
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                result = CommandResult(
                    command=command,
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    exit_code=-1,
                    success=False
                )
                return ToolResult(success=False, data=result, error="Command timeout")
                
        except Exception as e:
            result = CommandResult(
                command=command,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                success=False
            )
            return ToolResult(success=False, data=result, error=str(e))