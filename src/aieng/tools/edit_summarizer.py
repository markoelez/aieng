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
      # Group edits by file to avoid duplicates
      file_edits = {}

      for edit in applied_edits:
        file_path = edit.file_path

        if file_path not in file_edits:
          # First edit for this file
          if not edit.old_content.strip():
            file_edits[file_path] = {"action": "Created", "descriptions": []}
          elif edit.old_content == "REWRITE_ENTIRE_FILE":
            file_edits[file_path] = {"action": "Rewrote", "descriptions": []}
          else:
            file_edits[file_path] = {"action": "Updated", "descriptions": [edit.description]}
        else:
          # Additional edit for same file
          existing = file_edits[file_path]
          if existing["action"] == "Updated" and edit.description:
            # Add description if it's a partial update
            existing["descriptions"].append(edit.description)
          elif not edit.old_content.strip():
            # If we see a creation after other edits, it's probably a rewrite
            existing["action"] = "Rewrote"
            existing["descriptions"] = []
          elif edit.old_content == "REWRITE_ENTIRE_FILE":
            # Upgrade to rewrite
            existing["action"] = "Rewrote"
            existing["descriptions"] = []

      # Generate summary lines
      edit_descriptions = []
      for file_path, info in file_edits.items():
        action = info["action"]
        descriptions = info["descriptions"]

        if action in ["Created", "Rewrote"]:
          edit_descriptions.append(f"• {action} {file_path}")
        else:  # Updated
          if descriptions:
            # Show unique descriptions
            unique_descriptions = list(dict.fromkeys(descriptions))  # Remove duplicates while preserving order
            if len(unique_descriptions) == 1:
              edit_descriptions.append(f"• Updated {file_path}: {unique_descriptions[0]}")
            else:
              edit_descriptions.append(
                f"• Updated {file_path}: {', '.join(unique_descriptions[:2])}{'...' if len(unique_descriptions) > 2 else ''}"
              )
          else:
            edit_descriptions.append(f"• Updated {file_path}")

      # Return the bulleted list as the summary
      summary = "\n".join(edit_descriptions)
      return ToolResult(success=True, data=summary)

    except Exception as e:
      return ToolResult(success=True, data=f"Applied {len(applied_edits)} edit(s) successfully.")
