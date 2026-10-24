"""LLM Provider abstraction and concrete implementations."""

import abc
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class LLMResponse:
    """Standardized response from an LLM call."""

    def __init__(self, content: str, raw: Optional[Dict[str, Any]] = None):
        self.content = content
        self.raw = raw or {}

    def extract_python_code(self) -> str:
        """Extract Python code block from markdown response or raw text."""
        # Check for ```python ... ```
        pattern = r"```(?:python|py)?\n(.*?)```"
        matches = re.findall(pattern, self.content, re.DOTALL | re.IGNORECASE)
        if matches:
            return matches[0].strip()
        # If no markdown blocks, return stripped content
        return self.content.strip()

    def extract_json(self) -> Optional[Dict[str, Any]]:
        """Try to parse JSON object from text."""
        # Attempt direct JSON
        try:
            return json.loads(self.content.strip())
        except Exception:
            pass

        # Match ```json ... ```
        pattern = r"```(?:json)?\n(.*?)```"
        matches = re.findall(pattern, self.content, re.DOTALL | re.IGNORECASE)
        if matches:
            try:
                return json.loads(matches[0].strip())
            except Exception:
                pass
        return None


class BaseLLMProvider(abc.ABC):
    """Abstract interface for LLM provider implementations."""

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """Synchronously generate text response from the model."""
        pass


class OpenAILikeProvider(BaseLLMProvider):
    """LLM provider for OpenAI, DeepSeek, Groq, Ollama, or OpenAI-compatible endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")
        self.base_url = (
            base_url
            or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise ValueError("LLM_API_KEY is not configured for API provider.")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return LLMResponse(content=content, raw=data)
        except httpx.HTTPStatusError as e:
            logger.error("LLM API HTTP Error: %s - %s", e.response.status_code, e.response.text)
            raise RuntimeError(f"LLM API request failed: {e.response.status_code} {e.response.text}") from e
        except Exception as e:
            logger.error("LLM API Call failed: %s", str(e))
            raise RuntimeError(f"LLM communication error: {str(e)}") from e


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for offline testing and evaluation without paid API keys."""

    def __init__(self, response_script: Optional[Dict[str, str]] = None):
        self.response_script = response_script or {}
        self.call_history: List[Dict[str, Any]] = []

    def set_response(self, key_substring: str, response_content: str) -> None:
        self.response_script[key_substring] = response_content

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        self.call_history.append({"prompt": prompt, "system_prompt": system_prompt})

        # Match pre-scripted responses
        for key, response in self.response_script.items():
            if key in prompt or (system_prompt and key in system_prompt):
                return LLMResponse(content=response)

        # Default intelligent fallback for testing
        if "repair" in prompt.lower() or "fix" in prompt.lower():
            # Mock repair response
            code = (
                "def solve(nums):\n"
                "    \"\"\"Repaired solution.\"\"\"\n"
                "    return sorted(nums)\n"
            )
            return LLMResponse(
                content=f"### Explanation\nFixed the bug.\n\n```python\n{code}\n```"
            )
        elif "test" in prompt.lower():
            # Mock unit tests response
            test_code = (
                "import pytest\n"
                "from solution import solve\n\n"
                "def test_simple():\n"
                "    assert solve([3, 1, 2]) == [1, 2, 3]\n\n"
                "def test_empty():\n"
                "    assert solve([]) == []\n"
            )
            return LLMResponse(
                content=f"Here are the unit tests:\n\n```python\n{test_code}\n```"
            )
        else:
            # Mock initial generation response
            code = (
                "def solve(nums):\n"
                "    \"\"\"Initial solution.\"\"\"\n"
                "    return sorted(nums)\n"
            )
            return LLMResponse(
                content=f"### Approach\nWe sort the list.\n\n```python\n{code}\n```"
            )


def get_llm_provider() -> BaseLLMProvider:
    """Factory creating configured LLM provider according to environment variables."""
    provider_type = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider_type == "mock":
        return MockLLMProvider()
    elif provider_type in ("openai", "groq", "deepseek", "generic"):
        return OpenAILikeProvider()
    else:
        logger.warning("Unrecognized LLM_PROVIDER '%s'. Falling back to OpenAI compatible.", provider_type)
        return OpenAILikeProvider()
