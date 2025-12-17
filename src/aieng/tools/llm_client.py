"""LLM client tool."""

import os
import asyncio
from typing import Any, Dict, List, Callable, Optional, cast

from dotenv import load_dotenv
from openai import OpenAI

from .base import Tool, ToolResult
from ..config import DEFAULT_MODEL, API_KEY_ENV_VAR, DEFAULT_API_BASE_URL

load_dotenv()


class LLMClient(Tool):
  """Tool for interacting with LLM APIs."""

  def __init__(
    self,
    model: str = DEFAULT_MODEL,
    config: Optional[Dict[str, Any]] = None,
    ui_callback: Optional[Callable[..., None]] = None,
  ):
    super().__init__(ui_callback)

    if config is None:
      config = {}

    api_key = os.getenv(API_KEY_ENV_VAR)
    if not api_key:
      raise ValueError(f"{API_KEY_ENV_VAR} environment variable is required")

    api_base_url = config.get("api_base_url", DEFAULT_API_BASE_URL)
    self.client = OpenAI(api_key=api_key, base_url=api_base_url)
    self.model = model

  async def execute(
    self,
    messages: List[Dict[str, Any]],
    response_format: Optional[Dict[str, Any]] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
  ) -> ToolResult:
    """Execute LLM request with retry logic."""
    last_error = None

    self._notify_ui("start_loading")

    try:
      for attempt in range(max_retries):
        try:
          if attempt > 0:
            self._notify_ui("show_llm_retry", attempt, max_retries, str(last_error))

          llm_messages = self._prepare_messages(messages, response_format)
          kwargs = {"model": self.model, "input": llm_messages}

          if max_tokens:
            kwargs["max_output_tokens"] = max_tokens

          response = self.client.responses.create(**cast(Dict[str, Any], kwargs))

          if attempt > 0:
            self._notify_ui("show_llm_retry_success", attempt + 1)

          content = self._extract_response_text(response)
          if not content or not content.strip():
            raise ValueError(f"Empty response from LLM API on attempt {attempt + 1}")

          return ToolResult(success=True, data=content)

        except Exception as e:
          last_error = e
          if attempt < max_retries - 1:
            wait_time = 2**attempt
            await asyncio.sleep(wait_time)
          else:
            self._notify_ui("show_llm_retry_failed", max_retries, str(e))
            return ToolResult(success=False, error=str(e))

    finally:
      self._notify_ui("stop_loading")

    # Should be unreachable, but include a defensive fallback
    fallback_error = str(last_error) if last_error else "LLM request failed without a response"
    return ToolResult(success=False, error=fallback_error)

  def _prepare_messages(self, messages: List[Dict[str, Any]], response_format: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a copy of messages with additional instructions if needed."""
    if not response_format:
      return list(messages)

    response_type = response_format.get("type")
    if response_type not in {"json_object", "json_schema"}:
      return list(messages)

    json_instruction = {
      "role": "system",
      "content": (
        "You must respond with valid JSON that matches the user's requested schema. "
        "Do not include any natural language outside the JSON object."
      ),
    }

    # Insert the instruction before the user content to reinforce formatting
    return [json_instruction] + list(messages)

  def _extract_response_text(self, response: Any) -> str:
    """Extract text content from an OpenAI responses API result."""
    if response is None:
      return ""

    # The responses API exposes convenience output_text with concatenated text
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, list):
      cleaned = [text for text in output_text if isinstance(text, str) and text.strip()]
      if cleaned:
        return "\n\n".join(cleaned).strip()
    elif isinstance(output_text, str) and output_text.strip():
      return output_text.strip()

    texts = []

    output = getattr(response, "output", None) or []
    for item in output:
      # Items may contain nested content parts
      content_parts = getattr(item, "content", None) or []
      for part in content_parts:
        part_text = self._extract_text_value(part)
        if part_text:
          texts.append(part_text)

      # Some items expose text directly
      direct_text = self._extract_text_value(item)
      if direct_text:
        texts.append(direct_text)

    if texts:
      return "\n".join(t for t in texts if t).strip()

    # Fallback for legacy chat completion structure if returned
    choices = getattr(response, "choices", None)
    if choices:
      first_choice = choices[0]
      message = getattr(first_choice, "message", None)
      if message:
        content = getattr(message, "content", None)
        if isinstance(content, str):
          return content.strip()
        if isinstance(content, list):
          return "\n".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()

    return ""

  def _extract_text_value(self, obj: Any) -> str:
    """Best-effort extraction of textual content from response objects."""
    if obj is None:
      return ""

    text_attr = getattr(obj, "text", None)
    if isinstance(text_attr, str):
      return text_attr
    if hasattr(text_attr, "value"):
      return getattr(text_attr, "value") or ""

    if isinstance(obj, dict):
      if "text" in obj:
        text = obj["text"]
        if isinstance(text, dict) and "value" in text:
          return text.get("value") or ""
        if isinstance(text, str):
          return text
      if "value" in obj and isinstance(obj["value"], str):
        return obj["value"]

    # Fallback: if object itself is string-like
    if isinstance(obj, str):
      return obj

    return ""
