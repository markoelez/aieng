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
    import difflib

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

    # If old_content is empty, this is a new file creation
    if not edit.old_content.strip():
      if file_path.exists():
        return DiffResult(False, f"File already exists: {edit.file_path}")
      return DiffResult(True)

    # If old_content is the special rewrite marker, this is a complete file rewrite
    if edit.old_content == "REWRITE_ENTIRE_FILE":
      if not file_path.exists():
        return DiffResult(False, f"File does not exist: {edit.file_path}")
      return DiffResult(True)

    # For existing file edits
    if not file_path.exists():
      return DiffResult(False, f"File does not exist: {edit.file_path}")

    try:
      with open(file_path, "r", encoding="utf-8") as f:
        current_content = f.read()
    except Exception as e:
      return DiffResult(False, f"Error reading file {edit.file_path}: {e}")

    # Check if it's a complete file replacement (content matches when stripped)
    if edit.old_content.strip() == current_content.strip():
      return DiffResult(True)

    # Check if it's a partial replacement (content found in file)
    if edit.old_content in current_content:
      return DiffResult(True)

    # Content not found
    return DiffResult(False, f"Content validation will fail for {edit.file_path}")

  def apply_edit(self, edit: FileEdit) -> DiffResult:
    file_path = self.project_root / edit.file_path

    try:
      # Check if this is a directory creation (path ends with /)
      if edit.file_path.endswith('/'):
        # Create directory
        file_path.mkdir(parents=True, exist_ok=True)
        return DiffResult(True)
      
      # If old_content is empty, this is a new file creation
      if not edit.old_content.strip():
        # Ensure parent directories exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
          f.write(edit.new_content)
        return DiffResult(True)

      # If old_content is the special rewrite marker, replace entire file
      if edit.old_content == "REWRITE_ENTIRE_FILE":
        with open(file_path, "w", encoding="utf-8") as f:
          f.write(edit.new_content)
        return DiffResult(True)

      # For existing file edits
      with open(file_path, "r", encoding="utf-8") as f:
        current_content = f.read()

      # Check if old_content matches the entire file (complete rewrite)
      if edit.old_content.strip() == current_content.strip():
        # Complete file replacement
        with open(file_path, "w", encoding="utf-8") as f:
          f.write(edit.new_content)
        return DiffResult(True)

      # Check if old_content is found in the file (partial replacement)
      if edit.old_content in current_content:
        new_file_content = current_content.replace(edit.old_content, edit.new_content, 1)
        with open(file_path, "w", encoding="utf-8") as f:
          f.write(new_file_content)
        return DiffResult(True)

      # Content not found - provide detailed error
      old_preview = edit.old_content[:100] + "..." if len(edit.old_content) > 100 else edit.old_content
      file_preview = current_content[:100] + "..." if len(current_content) > 100 else current_content
      return DiffResult(
        False, f"Old content not found in {edit.file_path}.\nLooking for: {repr(old_preview)}\nFile starts with: {repr(file_preview)}"
      )

    except Exception as e:
      return DiffResult(False, f"Error applying edit to {edit.file_path}: {e}")

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

  def find_line_number(self, content: str, target_content: str) -> int:
    """Find the line number where target_content starts in content"""
    # First try exact string match to find position
    if target_content in content:
      # Count newlines before the match
      pos = content.find(target_content)
      line_num = content[:pos].count("\n") + 1
      return line_num

    # Fallback to line-by-line matching
    lines = content.splitlines()
    target_lines = target_content.splitlines()

    if not target_lines:
      return 1

    first_target_line = target_lines[0]

    for i, line in enumerate(lines):
      if line.strip() == first_target_line.strip():
        # Found potential match, check if following lines match too
        if len(target_lines) == 1:
          return i + 1  # Line numbers are 1-based

        # Check if subsequent lines match
        match = True
        for j, target_line in enumerate(target_lines[1:], 1):
          if i + j >= len(lines) or lines[i + j].strip() != target_line.strip():
            match = False
            break

        if match:
          return i + 1  # Line numbers are 1-based

    return 1  # Fallback

  def create_contextual_diff_with_line_numbers(self, file_content: str, old_text: str, new_text: str, file_path: str) -> str:
    """Create a diff showing the change in context with correct line numbers"""

    # Find where the old text appears in the file
    if old_text not in file_content:
      return f"Error: Cannot find old content in {file_path}"

    # Handle special case where old_text is empty or just whitespace
    if not old_text.strip():
      # For empty old content, try to find where the new content is being inserted
      # by creating the new file and seeing where it differs
      new_file_content = file_content.replace(old_text, new_text, 1)
      return self.create_standard_unified_diff(file_content, new_file_content, file_path)

    # Get the position and calculate line number
    pos = file_content.find(old_text)
    lines_before = file_content[:pos].count("\n")
    change_start_line = lines_before + 1  # Line numbers are 1-based

    # Split file into lines for context
    file_lines = file_content.splitlines()

    # Split the old and new text into lines
    old_text_lines = old_text.splitlines()
    new_text_lines = new_text.splitlines()

    # The change affects lines from change_start_line to change_start_line + len(old_text_lines) - 1
    change_end_line = change_start_line + len(old_text_lines) - 1

    # Add context around the change
    context = 3
    start_context = max(1, change_start_line - context)
    end_context = min(len(file_lines), change_end_line + context)

    # Build the diff
    diff_lines = []

    # Create @@ header with correct line numbers
    old_count = end_context - start_context + 1
    new_count = end_context - start_context + len(new_text_lines) - len(old_text_lines)
    diff_lines.append(f"@@ -{start_context},{old_count} +{start_context},{new_count} @@")

    # Add lines with proper diff formatting
    current_line = start_context

    # Context before change
    while current_line < change_start_line:
      if current_line <= len(file_lines):
        diff_lines.append(f" {file_lines[current_line - 1]}")  # -1 for 0-based indexing
      current_line += 1

    # The removed lines
    for old_line in old_text_lines:
      diff_lines.append(f"-{old_line}")

    # The added lines
    for new_line in new_text_lines:
      diff_lines.append(f"+{new_line}")

    # Context after change (use original file lines for context)
    current_line = change_end_line + 1
    while current_line <= end_context and current_line <= len(file_lines):
      diff_lines.append(f" {file_lines[current_line - 1]}")  # -1 for 0-based indexing
      current_line += 1

    return "\n".join(diff_lines)

  def create_standard_unified_diff(self, old_content: str, new_content: str, file_path: str) -> str:
    """Create a standard unified diff - this should have proper line numbers"""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
      old_lines,
      new_lines,
      fromfile=f"a/{file_path}",
      tofile=f"b/{file_path}",
      lineterm="",
      n=3,  # 3 lines of context
    )

    return "".join(diff)

  def create_diff_for_insertion(self, file_content: str, new_text: str, file_path: str) -> str:
    """Create a diff for inserting new content at the right location"""
    # This handles the case where old_content is empty/whitespace
    # We need to find where in the file the new content was actually inserted

    # Since old_content is empty, the new content is being inserted somewhere
    # Use the replacement to find the insertion point
    new_file_content = file_content.replace("", new_text, 1)  # This doesn't work well

    # Better approach: if old_content is empty, it's usually an append operation
    # Find where the content was actually added by comparing before/after
    if not new_text.strip():
      return "Error: Both old and new content are empty"

    # For insertions, assume it's being added at the end of a logical section
    # We'll show the context around where it's being inserted
    file_lines = file_content.splitlines()
    new_text_lines = new_text.splitlines()

    # Find the insertion point (this is a heuristic)
    # For pyproject.toml, it might be after dependencies
    insertion_line = len(file_lines)  # Default to end of file

    # Create diff showing insertion at the determined location
    context = 3
    start_context = max(1, insertion_line - context)
    end_context = insertion_line

    diff_lines = []

    # Create @@ header
    old_count = end_context - start_context + 1
    new_count = old_count + len(new_text_lines)
    diff_lines.append(f"@@ -{start_context},{old_count} +{start_context},{new_count} @@")

    # Add context before insertion
    for i in range(start_context, insertion_line + 1):
      if i <= len(file_lines):
        diff_lines.append(f" {file_lines[i - 1]}")  # -1 for 0-based indexing

    # Add the inserted lines
    for line in new_text_lines:
      diff_lines.append(f"+{line}")

    return "\n".join(diff_lines)

  def generate_enhanced_diff_text(self, old_content: str, new_content: str, file_path: str, change_start_line: int = None) -> str:
    """Generate diff with proper line number context"""
    # Try standard unified diff first
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
      old_lines,
      new_lines,
      fromfile=f"a/{file_path}",
      tofile=f"b/{file_path}",
      lineterm="",
      n=3,  # Add 3 lines of context
    )

    diff_text = "".join(diff)

    # Check if we got proper @@ headers
    if any(line.startswith("@@") for line in diff_text.split("\n")):
      return diff_text

    # If no @@ headers and we know the change location, create manual diff
    if change_start_line:
      return self.create_manual_diff(old_content, new_content, file_path, change_start_line)

    return diff_text

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
