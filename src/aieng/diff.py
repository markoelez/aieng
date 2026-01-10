import difflib
from typing import List, Optional
from pathlib import Path
from dataclasses import dataclass

from .agent import FileEdit


@dataclass
class DiffResult:
  success: bool
  error: Optional[str] = None


class DiffProcessor:
  def __init__(self, project_root: str = "."):
    self.project_root = Path(project_root).resolve()

  def generate_diff_text(self, old_content: str, new_content: str, file_path: str) -> str:
    """Generate a proper unified diff with correct line numbers"""
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    # Find the differences between old and new content
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

    # Build the diff manually with correct line numbers
    diff_lines = []
    context = 3

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
      if tag == "equal":
        continue

      # Found a difference - build the diff chunk
      # Calculate the line range with context
      start_old = max(0, i1 - context)
      end_old = min(len(old_lines), i2 + context)
      start_new = max(0, j1 - context)
      end_new = min(len(new_lines), j2 + context)

      # Create the @@ header with 1-based line numbers
      old_start = start_old + 1
      old_count = end_old - start_old
      new_start = start_new + 1
      new_count = end_new - start_new

      diff_lines.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@")

      # Add context lines before the change
      for idx in range(start_old, i1):
        if idx < len(old_lines):
          diff_lines.append(f" {old_lines[idx]}")

      # Add the actual changes
      if tag == "delete":
        for idx in range(i1, i2):
          diff_lines.append(f"-{old_lines[idx]}")
      elif tag == "insert":
        for idx in range(j1, j2):
          diff_lines.append(f"+{new_lines[idx]}")
      elif tag == "replace":
        # Show removals then additions
        for idx in range(i1, i2):
          diff_lines.append(f"-{old_lines[idx]}")
        for idx in range(j1, j2):
          diff_lines.append(f"+{new_lines[idx]}")

      # Add context lines after the change
      for idx in range(i2, end_old):
        if idx < len(old_lines):
          diff_lines.append(f" {old_lines[idx]}")

      # Only show the first difference for now
      break

    return "\n".join(diff_lines)

  def validate_edit(self, edit: FileEdit) -> DiffResult:
    file_path = self.project_root / edit.file_path

    # New file creation
    if not edit.old_content.strip():
      return DiffResult(False, f"File already exists: {edit.file_path}") if file_path.exists() else DiffResult(True)

    # Complete file rewrite
    if edit.old_content == "REWRITE_ENTIRE_FILE":
      return DiffResult(True) if file_path.exists() else DiffResult(False, f"File does not exist: {edit.file_path}")

    # Existing file edit
    if not file_path.exists():
      return DiffResult(False, f"File does not exist: {edit.file_path}")

    try:
      with open(file_path, "r", encoding="utf-8") as f:
        current_content = f.read()
    except Exception as e:
      return DiffResult(False, f"Error reading file {edit.file_path}: {e}")

    # Check for complete file replacement or partial replacement
    if edit.old_content.strip() == current_content.strip() or edit.old_content in current_content:
      return DiffResult(True)

    return DiffResult(False, f"Content validation will fail for {edit.file_path}")

  def apply_edit(self, edit: FileEdit) -> DiffResult:
    file_path = self.project_root / edit.file_path

    try:
      # Directory creation
      if edit.file_path.endswith("/"):
        file_path.mkdir(parents=True, exist_ok=True)
        return DiffResult(True)

      # New file creation
      if not edit.old_content.strip():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        return self._write_file(file_path, edit.new_content)

      # Complete file rewrite
      if edit.old_content == "REWRITE_ENTIRE_FILE":
        return self._write_file(file_path, edit.new_content)

      # Existing file edit
      with open(file_path, "r", encoding="utf-8") as f:
        current_content = f.read()

      # Complete file replacement
      if edit.old_content.strip() == current_content.strip():
        return self._write_file(file_path, edit.new_content)

      # Partial replacement
      if edit.old_content in current_content:
        new_content = current_content.replace(edit.old_content, edit.new_content, 1)
        return self._write_file(file_path, new_content)

      # Content not found
      old_preview = (edit.old_content[:100] + "...") if len(edit.old_content) > 100 else edit.old_content
      file_preview = (current_content[:100] + "...") if len(current_content) > 100 else current_content
      return DiffResult(
        False, f"Old content not found in {edit.file_path}.\nLooking for: {repr(old_preview)}\nFile starts with: {repr(file_preview)}"
      )

    except Exception as e:
      return DiffResult(False, f"Error applying edit to {edit.file_path}: {e}")

  def _write_file(self, file_path: Path, content: str) -> DiffResult:
    """Write content to a file and return success result."""
    with open(file_path, "w", encoding="utf-8") as f:
      f.write(content)
    return DiffResult(True)

  def apply_edits(self, edits: List[FileEdit]) -> List[DiffResult]:
    results = []
    for edit in edits:
      result = self.apply_edit(edit)
      results.append(result)
      if not result.success:
        break
    return results

  def create_new_file(self, file_path: str, content: str) -> DiffResult:
    full_path = self.project_root / file_path

    if full_path.exists():
      return DiffResult(False, f"File already exists: {file_path}")

    try:
      full_path.parent.mkdir(parents=True, exist_ok=True)

      with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

      return DiffResult(True)

    except Exception as e:
      return DiffResult(False, f"Error creating file {file_path}: {e}")

  def preview_edits(self, edits: List[FileEdit]) -> List[str]:
    previews = []

    for edit in edits:
      file_path = self.project_root / edit.file_path

      # Handle new file creation
      if not edit.old_content.strip():
        diff_text = self.generate_diff_text("", edit.new_content, edit.file_path)
        previews.append(diff_text)
        continue

      # Handle complete file rewrite
      if edit.old_content == "REWRITE_ENTIRE_FILE":
        if file_path.exists():
          try:
            with open(file_path, "r", encoding="utf-8") as f:
              current_content = f.read()
            diff_text = self.generate_diff_text(current_content, edit.new_content, edit.file_path)
            previews.append(diff_text)
          except Exception as e:
            previews.append(f"Error reading {edit.file_path}: {e}")
        else:
          previews.append(f"Error: File does not exist: {edit.file_path}")
        continue

      # Handle regular edits
      if file_path.exists():
        try:
          with open(file_path, "r", encoding="utf-8") as f:
            current_content = f.read()

          if edit.old_content in current_content:
            # Apply the edit and create standard unified diff
            new_file_content = current_content.replace(edit.old_content, edit.new_content, 1)
            diff_text = self.generate_diff_text(current_content, new_file_content, edit.file_path)
            previews.append(diff_text)
          elif edit.old_content.strip() == current_content.strip():
            # Complete file replacement
            diff_text = self.generate_diff_text(current_content, edit.new_content, edit.file_path)
            previews.append(diff_text)
          else:
            previews.append(f"Error: Old content not found in {edit.file_path}")

        except Exception as e:
          previews.append(f"Error reading {edit.file_path}: {e}")
      else:
        previews.append(f"Error: File does not exist: {edit.file_path}")

    return previews
