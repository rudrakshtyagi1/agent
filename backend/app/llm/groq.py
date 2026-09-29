"""Bounded Groq transport. Never log keys, request bodies, or provider error bodies."""

import asyncio
import json
import time
import httpx
from pydantic import BaseModel, Field, ConfigDict, ValidationError

URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3.8-27b"


class ProviderError(RuntimeError):
    pass


class BudgetExceeded(ProviderError):
    pass


class FunctionCall(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    arguments: str = Field(max_length=4000)


class ToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: str = "function"
    function: FunctionCall


class Message(BaseModel):
    role: str = "assistant"
    content: str | None = Field(default=None, max_length=12000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=4)


class GroqClient:
    def __init__(
        self, key, model=DEFAULT_MODEL, max_requests=4, interval_seconds=8, client=None
    ):
        if not key:
            raise ProviderError("GROQ_API_KEY is not configured")
        if not 1 <= max_requests <= 12 or not 0 <= interval_seconds <= 60:
            raise ValueError("Invalid provider budget")
        self._key = key
        self.model = model
        self.max_requests = max_requests
        self.interval_seconds = interval_seconds
        self.requests = 0
        self._last = 0
        self._client = client

    async def complete(self, messages, tools, trace):
        if len(json.dumps(messages)) > 24000:
            raise BudgetExceeded("Conversation exceeds the input character budget")
        if self.requests >= self.max_requests:
            raise BudgetExceeded("Provider request budget exhausted")
        delay = max(0, self.interval_seconds - (time.monotonic() - self._last))
        if delay:
            await asyncio.sleep(delay)
        self.requests += 1
        self._last = time.monotonic()
        with trace.span("groq_completion", "model") as span:
            span["metadata"] = {
                "provider": "groq",
                "model": self.model,
                "request_index": self.requests,
                "simulated": False,
            }
            body = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "parallel_tool_calls": False,
                "max_completion_tokens": 512,
                "temperature": 0,
                "reasoning_format": "hidden",
            }
            # Do not retry inference transparently: each retry would consume quota.
            try:
                if self._client is not None:
                    data = await self._send(self._client, body)
                else:
                    async with httpx.AsyncClient(
                        timeout=20, follow_redirects=False, trust_env=False
                    ) as client:
                        data = await self._send(client, body)
            except httpx.HTTPError:
                raise ProviderError(
                    "Groq network or timeout failure; no automatic inference retry"
                ) from None
            try:
                choices = data["choices"]
                if (
                    not isinstance(choices, list)
                    or not choices
                    or not isinstance(choices[0], dict)
                ):
                    raise ValueError()
                if len(choices) != 1 or choices[0].get("finish_reason") not in (
                    "stop",
                    "tool_calls",
                ):
                    raise ValueError()
                raw = choices[0]["message"]
                if not isinstance(raw, dict):
                    raise ValueError()
                if raw.get("tool_calls") is None:
                    raw = {**raw, "tool_calls": []}
                message = Message.model_validate(raw)
                if message.role != "assistant" or any(
                    t.type != "function" for t in message.tool_calls
                ):
                    raise ValueError()
                usage = data.get("usage") or {}
                if not isinstance(usage, dict):
                    raise ValueError()
                for destination, source in [
                    ("input_tokens", "prompt_tokens"),
                    ("output_tokens", "completion_tokens"),
                ]:
                    value = usage.get(source)
                    span[destination] = (
                        value
                        if type(value) is int and 0 <= value <= 100000000
                        else None
                    )
                # Discard reasoning and unknown provider fields rather than persisting them.
                result = message.model_dump(exclude_none=True)
                if not result.get("tool_calls"):
                    result.pop("tool_calls", None)
                span["output"] = {
                    "tool_names": [t.function.name for t in message.tool_calls],
                    "has_answer": bool(message.content),
                }
                return result
            except (KeyError, TypeError, ValueError, ValidationError):
                raise ProviderError(
                    "Groq returned an invalid or truncated completion"
                ) from None

    async def _send(self, client, body):
        async with client.stream(
            "POST", URL, headers={"Authorization": "Bearer " + self._key}, json=body
        ) as response:
            if response.status_code == 429:
                raise ProviderError(
                    "Groq free-tier quota reached (429); stop and retry later"
                )
            if response.status_code in (401, 403):
                raise ProviderError(
                    "Groq rejected authentication; check the local key and model access"
                )
            if response.status_code != 200:
                raise ProviderError(
                    f"Groq request failed (HTTP {response.status_code}); response body suppressed"
                )
            chunks = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 65536:
                    raise ProviderError("Groq response exceeded 64 KiB")
                chunks.append(chunk)
            try:
                return json.loads(b"".join(chunks))
            except (ValueError, UnicodeError):
                raise ProviderError("Groq returned invalid JSON") from None
