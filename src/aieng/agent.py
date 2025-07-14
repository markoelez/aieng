import os
import json
import time
import asyncio
import subprocess
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, field_validator

# Load environment variables from .env file
load_dotenv()


@dataclass
class FileEdit:
  file_path: str
  old_content: str
  new_content: str
  description: str


@dataclass
class SearchResult:
  query: str
  command: str
  results: str
  description: str


class LLMResponse(BaseModel):
  summary: str
  commands: List[Dict[str, str]] = []
  edits: List[Dict[str, str]]


class Todo(BaseModel):
  id: int
  task: str
  reasoning: str
  priority: str  # "high", "medium", "low"
  dependencies: List[int] = []  # IDs of todos this depends on


class TodoPlan(BaseModel):
  summary: str
  todos: List[Todo]


class CommandResult(BaseModel):
  command: str
  stdout: str
  stderr: str
  exit_code: int
  success: bool


class TodoResult(BaseModel):
  thinking: str
  commands: List[Dict[str, str]] = []
  searches: List[Dict[str, str]] = []
  edits: List[Dict[str, str]] = []
  completed: bool
  next_steps: Optional[str] = ""
  
  @field_validator('next_steps')
  @classmethod
  def validate_next_steps(cls, v):
    if v is None:
      return ""
    return str(v)
  
  @field_validator('commands')
  @classmethod
  def validate_commands(cls, v):
    if v is None:
      return []
    if not isinstance(v, list):
      return []
    # Ensure each command is a dictionary with required string fields
    validated_commands = []
    for cmd in v:
      if isinstance(cmd, dict):
        # Ensure required fields exist and are strings
        command_dict = {
          "command": str(cmd.get("command", "")),
          "description": str(cmd.get("description", ""))
        }
        validated_commands.append(command_dict)
    return validated_commands
  
  @field_validator('searches')
  @classmethod
  def validate_searches(cls, v):
    if v is None:
      return []
    if not isinstance(v, list):
      return []
    # Ensure each search is a dictionary with required string fields
    validated_searches = []
    for search in v:
      if isinstance(search, dict):
        search_dict = {
          "query": str(search.get("query", "")),
          "command": str(search.get("command", "")),
          "description": str(search.get("description", ""))
        }
        validated_searches.append(search_dict)
    return validated_searches
  
  @field_validator('edits')
  @classmethod
  def validate_edits(cls, v):
    if v is None:
      return []
    if not isinstance(v, list):
      return []
    # Ensure each edit is a dictionary with required string fields
    validated_edits = []
    for edit in v:
      if isinstance(edit, dict):
        edit_dict = {
          "file_path": str(edit.get("file_path", "")),
          "old_content": str(edit.get("old_content", "")),
          "new_content": str(edit.get("new_content", "")),
          "description": str(edit.get("description", ""))
        }
        validated_edits.append(edit_dict)
    return validated_edits


class Agent:
  def __init__(self, model: str = "grok-4", ui_callback: Optional[Callable] = None, project_root: str = ".", config: dict = None):
    # Get API configuration from config and environment variables
    if config is None:
      config = {}
    
    api_key = os.getenv("API_KEY")
    if not api_key:
      raise ValueError("API_KEY environment variable is required. Please set it in your .env file or environment.")

    api_base_url = config.get("api_base_url", "https://api.x.ai/v1")
    
    self.client = OpenAI(api_key=api_key, base_url=api_base_url)
    self.model = model
    self.ui_callback = ui_callback  # For showing retry messages
    self.project_root = os.path.abspath(project_root)

  async def _call_llm_with_retry(
    self, messages: List[Dict], response_format: Optional[Dict] = None, max_tokens: Optional[int] = None, max_retries: int = 3
  ) -> str:
    """Call LLM with exponential backoff retry logic"""
    last_error = None

    # Start loading indicator on first attempt
    if self.ui_callback:
      self.ui_callback("start_loading")

    try:
      for attempt in range(max_retries):
        try:
          # Show retry message if this isn't the first attempt
          if attempt > 0 and self.ui_callback:
            self.ui_callback("show_llm_retry", attempt, max_retries, str(last_error))

          kwargs = {"model": self.model, "messages": messages}

          if response_format:
            kwargs["response_format"] = response_format
          if max_tokens:
            kwargs["max_tokens"] = max_tokens

          response = self.client.chat.completions.create(**kwargs)

          # Show success message if we had retries
          if attempt > 0 and self.ui_callback:
            self.ui_callback("show_llm_retry_success", attempt + 1)

          return response.choices[0].message.content

        except Exception as e:
          last_error = e
          if attempt < max_retries - 1:
            # Exponential backoff: 1s, 2s, 4s
            wait_time = 2**attempt
            await asyncio.sleep(wait_time)
          else:
            # Final failure
            if self.ui_callback:
              self.ui_callback("show_llm_retry_failed", max_retries, str(e))
            raise e
    finally:
      # Always stop loading indicator
      if self.ui_callback:
        self.ui_callback("stop_loading")

  async def execute_command(self, command: str, timeout: int = 30) -> CommandResult:
    """Execute a terminal command safely in the project directory"""
    try:
      # Show command execution if UI callback is available
      if self.ui_callback:
        self.ui_callback("show_command_execution", command)
      
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
        
        # Show command result if UI callback is available
        if self.ui_callback:
          self.ui_callback("show_command_result", result)
        
        return result
        
      except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return CommandResult(
          command=command,
          stdout="",
          stderr=f"Command timed out after {timeout} seconds",
          exit_code=-1,
          success=False
        )
        
    except Exception as e:
      return CommandResult(
        command=command,
        stdout="",
        stderr=str(e),
        exit_code=-1,
        success=False
      )

  def _build_system_prompt(self) -> str:
    return """You are an AI coding assistant. When given a user request and file context, respond with a structured JSON containing:
1. "summary": A brief description of changes you're making
2. "commands": (optional) A list of terminal commands to run, each with:
   - "command": The shell command to execute
   - "description": Why you're running this command
3. "searches": (optional) A list of search operations to find specific content, each with:
   - "query": What you're searching for (human-readable)
   - "command": The bash command to execute (grep, find, ripgrep, etc.)
   - "description": Why you need this search information
4. "edits": A list of file edits, each with:
   - "file_path": The path to the file to edit
   - "old_content": The exact content to replace (must match exactly, including whitespace). For NEW FILES, use empty string ""
   - "new_content": The new content to replace it with (or full file content for new files)
   - "description": A brief description of this specific edit

SEARCH GUIDELINES:
- Use searches when you need to find specific content, functions, patterns, or files
- Only search if the information isn't already in the provided file context
- Examples: "grep -r 'specific_function' .", "find . -name '*.py' | head -10", "rg 'pattern' --type python"
- Search commands run in the project root directory and results are displayed to help guide your edits

COMMAND EXECUTION GUIDELINES:
- Use commands to run tests, check syntax, or perform other operations
- Examples: "pytest tests/", "python -m flake8", "npm test"
- Commands run in the project root directory
- Commands help you understand the codebase before making changes
- Use commands to verify your changes work (run tests, check syntax, etc.)

IMPORTANT EDITING GUIDELINES:
- For NEW FILES: Use empty string "" for old_content
- For SMALL CHANGES: Find a specific section, paragraph, or lines to replace
- For COMPLETE FILE REWRITES: Use "REWRITE_ENTIRE_FILE" as old_content and put the new file content in new_content
- Copy old_content EXACTLY from the file context, including all whitespace and newlines
- When the user asks to rewrite, restructure, or make major changes to a file, use "REWRITE_ENTIRE_FILE" mode
- Break large changes into multiple smaller edits if doing targeted changes

Only make necessary changes to implement the user's request.
"""

  def _build_user_prompt(self, user_request: str, file_contexts: List[Dict[str, str]]) -> str:
    prompt_parts = [f"User request: {user_request}\n"]

    if file_contexts:
      prompt_parts.append("File contexts:")
      for ctx in file_contexts:
        prompt_parts.append(f"\n--- {ctx['path']} ---")
        prompt_parts.append(ctx["content"])
        prompt_parts.append("--- End ---\n")

    prompt_parts.append("\nRespond with valid JSON only.")
    return "\n".join(prompt_parts)

  async def process_request(self, user_request: str, file_contexts: List[Dict[str, str]]) -> LLMResponse:
    try:
      messages = [
        {"role": "system", "content": self._build_system_prompt()},
        {"role": "user", "content": self._build_user_prompt(user_request, file_contexts)},
      ]

      content = await self._call_llm_with_retry(messages=messages, response_format={"type": "json_object"})

      parsed = json.loads(content)
      return LLMResponse(**parsed)

    except Exception as e:
      raise Exception(f"Error processing LLM request: {e}")

  def parse_edits(self, llm_response: LLMResponse) -> List[FileEdit]:
    edits = []
    for edit_data in llm_response.edits:
      edit = FileEdit(
        file_path=edit_data["file_path"],
        old_content=edit_data["old_content"],
        new_content=edit_data["new_content"],
        description=edit_data["description"],
      )
      edits.append(edit)
    return edits

  async def generate_todo_plan(self, user_request: str, file_contexts: List[Dict[str, str]]) -> TodoPlan:
    """Generate a plan of todos to accomplish the user's request"""
    try:
      context_summary = "\n".join([f"- {ctx['path']}: {len(ctx['content'])} chars" for ctx in file_contexts])

      planning_prompt = f"""
Break down this request into 1-3 concise action items.

Request: {user_request}

Files: {context_summary}

Create JSON with:
- "summary": Brief plan overview (max 10 words)
- "todos": List with:
  - "id": Number (1, 2, 3...)
  - "task": Short, direct action (max 8 words, e.g. "Add tests", "Update README", "Fix login bug")
  - "reasoning": Brief why (max 6 words)
  - "priority": "high", "medium", or "low" 
  - "dependencies": Array of prerequisite todo IDs

Keep todos:
- Ultra-concise and actionable
- Focus on specific deliverables
- Avoid verbose descriptions

Example bad: "Create comprehensive unit tests for user authentication functions with proper mocking"
Example good: "Add user auth tests"
"""

      messages = [
        {"role": "system", "content": "You create concise, targeted action plans. Avoid verbose explanations."},
        {"role": "user", "content": planning_prompt},
      ]

      content = await self._call_llm_with_retry(messages=messages, response_format={"type": "json_object"})
      parsed = json.loads(content)
      return TodoPlan(**parsed)

    except Exception as e:
      # Fallback to simple single todo
      return TodoPlan(
        summary=f"Simple plan for: {user_request}",
        todos=[Todo(id=1, task=user_request, reasoning="Direct implementation of user request", priority="high", dependencies=[])],
      )

  async def process_todo(
    self, todo: Todo, user_request: str, file_contexts: List[Dict[str, str]], completed_todos: List[Todo] = None
  ) -> TodoResult:
    """Process a single todo with chain-of-thought reasoning"""
    if completed_todos is None:
      completed_todos = []

    try:
      # Build context about completed work
      completed_context = ""
      if completed_todos:
        completed_context = "Previously completed todos:\n" + "\n".join([f"- {t.task}" for t in completed_todos]) + "\n\n"

      context_info = "\n".join(
        [
          f"--- {ctx['path']} ---\n{ctx['content'][:1000]}..." if len(ctx["content"]) > 1000 else f"--- {ctx['path']} ---\n{ctx['content']}"
          for ctx in file_contexts
        ]
      )

      todo_prompt = f"""
You are an AI coding assistant working on this specific todo item.

Original user request: {user_request}
Current todo: {todo.task}
Reasoning: {todo.reasoning}

{completed_context}File contexts:
{context_info}

INSTRUCTIONS:
1. Think step-by-step about how to complete this specific todo
2. Use the provided file contexts to understand the codebase
3. Generate the necessary file edits to complete this todo immediately
4. Mark the todo as completed if you have generated all necessary edits

CRITICAL RULES:
- AVOID running commands unless absolutely necessary (like creating directories)
- AVOID searches unless the exact information you need is missing from file contexts
- FOCUS on generating file edits to complete the task
- If a todo asks to "add tests", "create files", or "modify code", generate the actual edits immediately
- Don't over-analyze - if you have enough context, make the edits

Respond with JSON containing:
- "thinking": Your step-by-step reasoning about how to complete this todo
- "searches": List of search operations (USE SPARINGLY - only if critical info missing from contexts)
- "commands": List of terminal commands (USE SPARINGLY - only for mkdir, etc.)
- "edits": List of file edits needed - THIS IS THE MAIN FOCUS, GENERATE THESE TO COMPLETE THE TODO
- "completed": true if this todo is fully completed with edits, false only if you genuinely cannot proceed
- "next_steps": What should happen next (only if completed=false)

For edits (THE PRIMARY OUTPUT), each edit must have these fields:
- "file_path": Path to the file (can be new or existing)
- "old_content": Use "REWRITE_ENTIRE_FILE" for existing files, "" for new files
- "new_content": The complete new content of the file
- "description": Brief description of what this edit does

PRODUCTIVITY TIPS:
- The file contexts provide sufficient information for most tasks
- Generate edits immediately rather than searching for more information
- Focus on completing the todo with concrete file changes
- Avoid unnecessary exploration - be decisive and productive
"""

      messages = [
        {"role": "system", "content": "You are an expert software engineer who completes tasks efficiently by generating file edits. You are decisive, productive, and focus on delivering working code rather than excessive analysis."},
        {"role": "user", "content": todo_prompt},
      ]

      content = await self._call_llm_with_retry(messages=messages, response_format={"type": "json_object"})
      
      try:
        parsed = json.loads(content)
      except json.JSONDecodeError as e:
        # Fallback if JSON is malformed
        return TodoResult(
          thinking=f"JSON decode error: {e}", 
          edits=[], 
          completed=False, 
          next_steps="Fix JSON formatting and retry"
        )
      
      # Clean the parsed data before validation
      cleaned_parsed = {
        "thinking": str(parsed.get("thinking", "")),
        "commands": parsed.get("commands", []),
        "searches": parsed.get("searches", []),
        "edits": parsed.get("edits", []),
        "completed": bool(parsed.get("completed", False)),
        "next_steps": ""  # Will be cleaned below
      }
      
      # Handle next_steps which might be incorrectly formatted as a list
      next_steps_raw = parsed.get("next_steps", "")
      if isinstance(next_steps_raw, list):
        # Convert list to string
        if next_steps_raw:
          cleaned_parsed["next_steps"] = " ".join(str(item) for item in next_steps_raw)
        else:
          cleaned_parsed["next_steps"] = ""
      elif isinstance(next_steps_raw, str):
        cleaned_parsed["next_steps"] = next_steps_raw
      else:
        cleaned_parsed["next_steps"] = str(next_steps_raw) if next_steps_raw else ""
      
      # Ensure commands is a list of dicts
      if isinstance(cleaned_parsed["commands"], list):
        clean_commands = []
        for cmd in cleaned_parsed["commands"]:
          if isinstance(cmd, dict):
            clean_commands.append({
              "command": str(cmd.get("command", "")),
              "description": str(cmd.get("description", ""))
            })
          elif isinstance(cmd, str):
            # Handle case where command is just a string
            clean_commands.append({
              "command": cmd,
              "description": "Command execution"
            })
        cleaned_parsed["commands"] = clean_commands
      else:
        cleaned_parsed["commands"] = []
      
      # Ensure searches is a list of dicts
      if isinstance(cleaned_parsed["searches"], list):
        clean_searches = []
        for search in cleaned_parsed["searches"]:
          if isinstance(search, dict):
            clean_searches.append({
              "query": str(search.get("query", "")),
              "command": str(search.get("command", "")),
              "description": str(search.get("description", ""))
            })
        cleaned_parsed["searches"] = clean_searches
      else:
        cleaned_parsed["searches"] = []
      
      # Ensure edits is a list of dicts
      if isinstance(cleaned_parsed["edits"], list):
        clean_edits = []
        for edit in cleaned_parsed["edits"]:
          if isinstance(edit, dict):
            clean_edits.append({
              "file_path": str(edit.get("file_path", "")),
              "old_content": str(edit.get("old_content", "")),
              "new_content": str(edit.get("new_content", "")),
              "description": str(edit.get("description", ""))
            })
        cleaned_parsed["edits"] = clean_edits
      else:
        cleaned_parsed["edits"] = []
      
      return TodoResult(**cleaned_parsed)

    except Exception as e:
      return TodoResult(
        thinking=f"Error processing todo: {e}", edits=[], completed=False, next_steps="Retry or break down into smaller tasks"
      )

  async def generate_edit_summary(self, applied_edits: List[FileEdit], user_request: str) -> str:
    """Generate a concise summary of the edits that were applied"""
    try:
      edit_descriptions = []
      for edit in applied_edits:
        if not edit.old_content.strip():
          edit_descriptions.append(f"Created {edit.file_path}")
        else:
          edit_descriptions.append(f"Modified {edit.file_path}: {edit.description}")

      summary_prompt = f"""
      Original user request: {user_request}
      
      Edits that were applied:
      {chr(10).join(edit_descriptions)}
      
      Provide a concise 1-2 sentence summary of what was accomplished.
      """

      messages = [
        {"role": "system", "content": "You are a helpful assistant that summarizes code changes. Be concise and specific."},
        {"role": "user", "content": summary_prompt},
      ]

      content = await self._call_llm_with_retry(messages=messages, max_tokens=100)
      
      # Ensure we have a non-empty summary
      summary = content.strip() if content else ""
      if not summary:
        # Fallback to a descriptive summary based on the edits
        if len(edit_descriptions) == 1:
          summary = edit_descriptions[0]
        else:
          summary = f"Applied {len(applied_edits)} changes: {', '.join(edit_descriptions[:2])}{'...' if len(edit_descriptions) > 2 else ''}"
      
      return summary

    except Exception as e:
      return f"Applied {len(applied_edits)} edit(s) successfully."
