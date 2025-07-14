import fnmatch
from typing import Dict, List
from pathlib import Path

import git


class FileContextManager:
  def __init__(self, project_root: str = "."):
    self.project_root = Path(project_root).resolve()
    self.ignore_patterns = [
      "*.pyc",
      "__pycache__",
      ".git",
      ".venv/*",
      "venv/*",
      "node_modules",
      "*.egg-info",
      ".pytest_cache",
      ".coverage",
      "*.log",
      "*.tmp",
      ".DS_Store",
      "*.min.js",
      "*.min.css",
      "dist",
      "build",
      ".venv",
      "venv",
    ]
    self.max_file_size = 100000  # 100KB limit per file
    self.max_total_context = 500000  # 500KB total context limit

  def _should_ignore(self, file_path: Path) -> bool:
    # Check if any parent directory should be ignored
    path_parts = file_path.relative_to(self.project_root).parts

    # Check for specific directories to ignore
    ignore_dirs = {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}
    if any(part in ignore_dirs for part in path_parts):
      return True

    # Check file patterns
    for pattern in self.ignore_patterns:
      if fnmatch.fnmatch(file_path.name, pattern):
        return True

    return False

  def _is_text_file(self, file_path: Path) -> bool:
    try:
      with open(file_path, "rb") as f:
        chunk = f.read(512)
        return b"\0" not in chunk
    except:
      return False

  def _get_file_relevance_score(self, file_path: Path, keywords: List[str]) -> float:
    score = 0.0
    file_name = file_path.name.lower()
    file_content = ""

    try:
      with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read(self.max_file_size).lower()
    except:
      return 0.0

    # Score based on file extension
    if file_path.suffix in [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h"]:
      score += 1.0
    elif file_path.suffix in [".md", ".txt", ".rst"]:
      score += 0.3

    # Score based on keywords in filename
    for keyword in keywords:
      if keyword.lower() in file_name:
        score += 2.0

    # Score based on keywords in content
    for keyword in keywords:
      if keyword.lower() in file_content:
        score += 1.0

    return score

  def find_relevant_files(self, user_request: str, max_files: int = 15) -> List[Path]:
    keywords = user_request.lower().split()
    keywords = [word.strip(".,!?;:") for word in keywords if len(word) > 2]

    file_scores = []

    for file_path in self.project_root.rglob("*"):
      if (
        file_path.is_file()
        and not self._should_ignore(file_path)
        and self._is_text_file(file_path)
        and file_path.stat().st_size <= self.max_file_size
      ):
        score = self._get_file_relevance_score(file_path, keywords)
        if score > 0:
          file_scores.append((file_path, score))

    # Sort by score and return top files
    file_scores.sort(key=lambda x: x[1], reverse=True)
    return [file_path for file_path, _ in file_scores[:max_files]]

  def get_file_context(self, file_paths: List[Path]) -> List[Dict[str, str]]:
    contexts = []
    total_size = 0

    for file_path in file_paths:
      if total_size >= self.max_total_context:
        break

      try:
        with open(file_path, "r", encoding="utf-8") as f:
          content = f.read(self.max_file_size)

        if total_size + len(content) > self.max_total_context:
          remaining = self.max_total_context - total_size
          content = content[:remaining] + "\n... [truncated]"

        contexts.append({"path": str(file_path.relative_to(self.project_root)), "content": content})

        total_size += len(content)

      except Exception as e:
        contexts.append({"path": str(file_path.relative_to(self.project_root)), "content": f"Error reading file: {e}"})

    return contexts

  def get_git_context(self) -> Dict[str, str]:
    try:
      repo = git.Repo(self.project_root)

      # Get recent commits
      commits = list(repo.iter_commits(max_count=5))
      commit_info = []
      for commit in commits:
        commit_info.append(f"{commit.hexsha[:8]}: {commit.message.strip()}")

      # Get current branch and status
      branch = repo.active_branch.name
      status = repo.git.status("--porcelain")

      return {"branch": branch, "recent_commits": "\n".join(commit_info), "status": status}
    except:
      return {"error": "Not a git repository or git not available"}

  def build_context(self, user_request: str, specific_files: List[str] = None) -> List[Dict[str, str]]:
    if specific_files:
      file_paths = [self.project_root / file for file in specific_files]
      file_paths = [p for p in file_paths if p.exists()]
    else:
      file_paths = self.find_relevant_files(user_request)
      
      # For testing-related requests, ensure we get complete context for source files
      if any(keyword in user_request.lower() for keyword in ["test", "testing", "unittest", "pytest"]):
        # Prioritize source files that need testing by putting them first
        src_files = [p for p in file_paths if "/src/" in str(p) and p.suffix == ".py"]
        other_files = [p for p in file_paths if p not in src_files]
        file_paths = src_files + other_files

    return self.get_file_context(file_paths)
