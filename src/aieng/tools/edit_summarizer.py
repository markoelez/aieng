"""Edit summarization tool."""

from typing import List

from .base import Tool, ToolResult
from .llm_client import LLMClient
from ..models import FileEdit


class EditSummarizer(Tool):
    """Tool for summarizing applied edits."""
    
    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client.ui_callback)
        self.llm_client = llm_client
    
    async def execute(self, applied_edits: List[FileEdit], user_request: str) -> ToolResult:
        """Generate a concise summary of applied edits."""
        try:
            # Generate bulleted list directly without LLM
            edit_descriptions = []
            for edit in applied_edits:
                if not edit.old_content.strip():
                    edit_descriptions.append(f"• Created {edit.file_path}")
                elif edit.old_content == "REWRITE_ENTIRE_FILE":
                    edit_descriptions.append(f"• Rewrote {edit.file_path}")
                else:
                    # For partial edits, show what was changed
                    edit_descriptions.append(f"• Updated {edit.file_path}: {edit.description}")
            
            # Return the bulleted list as the summary
            summary = "\n".join(edit_descriptions)
            return ToolResult(success=True, data=summary)
            
        except Exception as e:
            return ToolResult(success=True, data=f"Applied {len(applied_edits)} edit(s) successfully.")