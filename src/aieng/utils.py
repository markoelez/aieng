"""Utility functions for the AI coding agent."""

import json
from typing import Dict, Any


def parse_llm_json(response_text: str) -> Dict[Any, Any]:
    """
    Parse JSON from LLM response, handling markdown code blocks.
    
    Many LLM providers wrap JSON responses in markdown code blocks like:
    ```json
    { "key": "value" }
    ```
    
    This function handles both wrapped and unwrapped JSON responses.
    """
    if not response_text:
        raise json.JSONDecodeError("Empty response", response_text, 0)
    
    # Clean the response - remove markdown code blocks if present
    cleaned_text = response_text.strip()
    
    if cleaned_text.startswith("```json"):
        # Remove ```json at start and ``` at end
        cleaned_text = cleaned_text[7:]  # Remove ```json
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]  # Remove ```
    elif cleaned_text.startswith("```"):
        # Remove ``` at start and end
        cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
    
    cleaned_text = cleaned_text.strip()
    
    # Parse the cleaned JSON
    return json.loads(cleaned_text)