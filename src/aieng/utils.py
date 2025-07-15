"""Utility functions for the AI coding agent."""

import json
import re
from typing import Any, Dict


def parse_llm_json(response_text: str) -> Dict[Any, Any]:
  """
  Parse JSON from LLM response, handling markdown code blocks and mixed text.

  Many LLM providers wrap JSON responses in markdown code blocks like:
  ```json
  { "key": "value" }
  ```

  This function handles both wrapped and unwrapped JSON responses, and also
  extracts JSON from mixed text responses.
  """
  if not response_text or not response_text.strip():
    raise json.JSONDecodeError("Empty or whitespace-only response", response_text or "", 0)

  # First try to extract JSON from anywhere in the response using regex
  
  # Look for JSON blocks within ``` markers
  json_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
  json_match = re.search(json_block_pattern, response_text, re.DOTALL)
  
  if json_match:
    cleaned_text = json_match.group(1).strip()
  else:
    # Look for standalone JSON objects (starting with { and ending with })
    # This pattern looks for balanced braces
    json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
    json_matches = re.findall(json_pattern, response_text, re.DOTALL)
    
    if json_matches:
      # Try each match until we find valid JSON
      for match in json_matches:
        try:
          return json.loads(match.strip())
        except json.JSONDecodeError:
          continue
      # If no matches were valid JSON, use the last one for error reporting
      cleaned_text = json_matches[-1].strip()
    else:
      # Fallback to original cleaning logic
      cleaned_text = response_text.strip()
      
      if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
          cleaned_text = cleaned_text[:-3]
      elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
          cleaned_text = cleaned_text[:-3]
      
      cleaned_text = cleaned_text.strip()
  
  # Additional check after cleaning
  if not cleaned_text:
    raise json.JSONDecodeError("Empty response after cleaning markdown", response_text, 0)

  # Parse the cleaned JSON
  try:
    return json.loads(cleaned_text)
  except json.JSONDecodeError as e:
    # Provide more context in error message
    print(f"Invalid JSON: {e.msg}. Raw response:\n{response_text}")
    exit(0)
    raise json.JSONDecodeError(f"Invalid JSON: {e.msg}. Raw response:\n{response_text}", cleaned_text, e.pos)