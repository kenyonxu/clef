"""Unified Chat client supporting both OpenAI and Anthropic Messages API formats.

Detects the API format based on base_url and handles conversion automatically.
- OpenAI: /chat/completions with Bearer auth
- Anthropic: /v1/messages with x-api-key + anthropic-version headers
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from agent_framework import ChatResponse, Content, Message
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientContentFilterException,
)

logger = logging.getLogger(__name__)


def _is_anthropic_endpoint(base_url: str) -> bool:
    """Detect Anthropic Messages API from base_url path."""
    lower = base_url.lower()
    return "/anthropic" in lower or "/messages" in lower


class ChatCompletionsClient:
    """Chat client supporting OpenAI Chat Completions and Anthropic Messages APIs."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._is_anthropic = _is_anthropic_endpoint(base_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send messages and return a ChatResponse (format auto-detected)."""
        if stream:
            raise NotImplementedError("Streaming not yet supported")

        if self._is_anthropic:
            return await self._call_anthropic(messages, tools=tools, **kwargs)
        return await self._call_openai(messages, tools=tools, **kwargs)

    # ------------------------------------------------------------------
    # OpenAI Chat Completions format
    # ------------------------------------------------------------------

    def _convert_messages_openai(self, messages: list[Message]) -> list[dict]:
        """Convert AF Messages to OpenAI chat-completions format."""
        openai_messages: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.role
            text_parts: list[str] = []
            tool_calls_list: list[dict] = []

            for content in msg.contents:
                ctype = getattr(content, "type", None)
                if ctype == "function_call":
                    tool_calls_list.append({
                        "id": getattr(content, "call_id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(content, "name", ""),
                            "arguments": getattr(content, "arguments", "{}"),
                        },
                    })
                elif ctype == "function_result":
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": getattr(content, "call_id", ""),
                        "content": str(getattr(content, "result", "")),
                    })
                else:
                    text_parts.append(str(content))

            if text_parts or tool_calls_list:
                entry: dict[str, Any] = {"role": role}
                if text_parts:
                    entry["content"] = "\n".join(text_parts)
                if tool_calls_list:
                    entry["tool_calls"] = tool_calls_list
                openai_messages.append(entry)

        return openai_messages

    async def _call_openai(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Call OpenAI Chat Completions API."""
        openai_messages = self._convert_messages_openai(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
        }

        if tools:
            payload["tools"] = tools
            if kwargs.get("tool_choice"):
                payload["tool_choice"] = kwargs["tool_choice"]

        data = await self._http_post(
            f"{self._base_url}/chat/completions",
            payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

        # Parse OpenAI response
        choice = data["choices"][0]
        msg_data = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        assistant_content: list[Any] = []
        if msg_data.get("content"):
            assistant_content.append(msg_data["content"])

        # Handle tool calls
        for tc in msg_data.get("tool_calls", []):
            fc = Content.from_function_call(
                call_id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"],
            )
            assistant_content.append(fc)

        return self._build_response(assistant_content, finish_reason, data)

    # ------------------------------------------------------------------
    # Anthropic Messages API format
    # ------------------------------------------------------------------

    def _convert_messages_anthropic(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict]]:
        """Convert AF Messages to Anthropic Messages API format.

        Returns (system_prompt, anthropic_messages).
        System role messages are extracted separately (Anthropic uses `system` field).
        """
        system_text: list[str] = []
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                for content in msg.contents:
                    system_text.append(str(content))
                continue

            role = msg.role
            text_parts: list[str] = []
            content_blocks: list[dict[str, Any]] = []

            for content in msg.contents:
                ctype = getattr(content, "type", None)
                if ctype == "function_call":
                    # Assistant's tool use → Anthropic tool_use block
                    args = getattr(content, "arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": getattr(content, "call_id", ""),
                        "name": getattr(content, "name", ""),
                        "input": args,
                    })
                elif ctype == "function_result":
                    # Tool result → Anthropic user message with tool_result block
                    content_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": getattr(content, "call_id", ""),
                        "content": str(getattr(content, "result", "")),
                    })
                else:
                    text_parts.append(str(content))

            # Build Anthropic message entry
            msg_blocks: list[dict[str, Any]] = []
            if text_parts:
                msg_blocks.append({
                    "type": "text",
                    "text": "\n".join(text_parts),
                })
            msg_blocks.extend(content_blocks)

            if msg_blocks:
                # Anthropic tool results must be in user role
                if role == "tool":
                    role = "user"
                anthropic_messages.append({"role": role, "content": msg_blocks})

        system = "\n".join(system_text) if system_text else None
        return system, anthropic_messages

    def _convert_tools_anthropic(
        self, tools: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        """Convert OpenAI-format tool schemas to Anthropic format."""
        if not tools:
            return None
        anthropic_tools = []
        for t in tools:
            func = t.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    async def _call_anthropic(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Call Anthropic Messages API."""
        system_prompt, anthropic_messages = self._convert_messages_anthropic(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
        }

        if system_prompt:
            payload["system"] = system_prompt

        temperature = kwargs.get("temperature", self._temperature)
        if temperature is not None:
            payload["temperature"] = temperature

        anthropic_tools = self._convert_tools_anthropic(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        data = await self._http_post(
            f"{self._base_url}/v1/messages",
            payload,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )

        # Parse Anthropic response
        finish_reason = data.get("stop_reason", "end_turn")
        assistant_content: list[Any] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                assistant_content.append(block["text"])
            elif block.get("type") == "tool_use":
                arguments = block.get("input", {})
                if isinstance(arguments, dict):
                    arguments = json.dumps(arguments)
                fc = Content.from_function_call(
                    call_id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=arguments,
                )
                assistant_content.append(fc)

        return self._build_response(assistant_content, finish_reason, data)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _http_post(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str],
    ) -> dict:
        """POST JSON with retry logic. Returns parsed JSON response."""
        timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
        max_retries = 3

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    # 500 errors get longer backoff (10s) vs standard exponential
                    backoff = 10 if status == 500 else 2 ** attempt
                    logger.warning(
                        "Server error %d on attempt %d/%d, retrying in %ds...",
                        status, attempt + 1, max_retries, backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                body = e.response.text
                if status in (401, 403):
                    raise ChatClientInvalidAuthException(
                        f"Authentication failed ({status}): {body}"
                    )
                if status == 400 and "content_filter" in body:
                    raise ChatClientContentFilterException(
                        f"Content filter triggered: {body}"
                    )
                raise ChatClientException(
                    f"API error ({status}): {body}"
                )
            except (
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
            ) as e:
                logger.warning(
                    "Transient error on attempt %d/%d: %s",
                    attempt + 1, max_retries, e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ChatClientException(f"Request failed: {e}")

        raise ChatClientException("Max retries exceeded")

    def _build_response(
        self,
        assistant_content: list[Any],
        finish_reason: str,
        raw_data: dict,
    ) -> ChatResponse:
        """Build ChatResponse from parsed content."""
        response_msg = Message(
            role="assistant",
            contents=assistant_content,
        )

        usage = raw_data.get("usage", {})
        usage_details = None
        if usage:
            from agent_framework import UsageDetails
            usage_details = UsageDetails(
                prompt_tokens=usage.get("input_tokens", usage.get("prompt_tokens", 0)),
                completion_tokens=usage.get("output_tokens", usage.get("completion_tokens", 0)),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                if "input_tokens" in usage
                else usage.get("total_tokens", 0),
            )

        return ChatResponse(
            messages=[response_msg],
            finish_reason=finish_reason,
            model=raw_data.get("model", self._model),
            usage_details=usage_details,
        )
