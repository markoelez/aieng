"""LLM client tool."""

import asyncio
import os
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .base import Tool, ToolResult

load_dotenv()


class LLMClient(Tool):
    """Tool for interacting with LLM APIs."""
    
    def __init__(self, model: str = "grok-4", config: Optional[Dict] = None, ui_callback: Optional[callable] = None):
        super().__init__(ui_callback)
        
        if config is None:
            config = {}
        
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise ValueError("API_KEY environment variable is required")
        
        api_base_url = config.get("api_base_url", "https://api.x.ai/v1")
        self.client = OpenAI(api_key=api_key, base_url=api_base_url)
        self.model = model
    
    async def execute(self, messages: List[Dict], response_format: Optional[Dict] = None, 
                     max_tokens: Optional[int] = None, max_retries: int = 3) -> ToolResult:
        """Execute LLM request with retry logic."""
        last_error = None
        
        self._notify_ui("start_loading")
        
        try:
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        self._notify_ui("show_llm_retry", attempt, max_retries, str(last_error))
                    
                    kwargs = {"model": self.model, "messages": messages}
                    
                    if response_format:
                        kwargs["response_format"] = response_format
                    if max_tokens:
                        kwargs["max_tokens"] = max_tokens
                    
                    response = self.client.chat.completions.create(**kwargs)
                    
                    if attempt > 0:
                        self._notify_ui("show_llm_retry_success", attempt + 1)
                    
                    return ToolResult(success=True, data=response.choices[0].message.content)
                    
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                    else:
                        self._notify_ui("show_llm_retry_failed", max_retries, str(e))
                        return ToolResult(success=False, error=str(e))
                        
        finally:
            self._notify_ui("stop_loading")