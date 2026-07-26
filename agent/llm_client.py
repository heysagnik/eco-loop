from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from openai import APIError, OpenAI
from openai import RateLimitError as OpenAIRateLimitError

load_dotenv()

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")

TEMPERATURE = 0.0
SEED = 42
OLLAMA_REQUEST_TIMEOUT_SECONDS = 180.0

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMCallError(Exception):
    

    pass
class LLMRateLimitError(LLMCallError):
    

    pass
def _parse_tool_calls(message) -> list[dict]:
    tool_calls = []
    for call in message.tool_calls or []:
        tool_calls.append({
            "id": call.id,
            "name": call.function.name,
            "arguments": json.loads(call.function.arguments),
        })
    return tool_calls


class OllamaLLMClient:
    

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

    def call(self, messages: list[dict], tools: list[dict], tool_choice: str | dict = "auto") -> dict:
        try:
            response = self._client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=TEMPERATURE,
                seed=SEED,
                timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS,
            )
            message = response.choices[0].message
            total_tokens = response.usage.total_tokens if response.usage else 0
            content = _THINK_BLOCK.sub("", message.content or "").strip()
            return {"content": content, "tool_calls": _parse_tool_calls(message), "total_tokens": total_tokens}
        except OpenAIRateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except (APIError, json.JSONDecodeError, ConnectionError) as exc:
            raise LLMCallError(str(exc)) from exc


def get_llm_client(provider: str | None = None) -> OllamaLLMClient:
    
    provider = provider or os.environ.get("LLM_PROVIDER", "ollama")
    if provider != "ollama":
        raise ValueError(f"unsupported LLM_PROVIDER '{provider}' - only 'ollama' is implemented")
    return OllamaLLMClient()


LLMClient = OllamaLLMClient
