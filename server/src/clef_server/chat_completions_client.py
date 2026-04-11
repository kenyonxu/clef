"""Lightweight Chat Completions client for OpenAI-compatible APIs (e.g. SiliconFlow).

The Agent Framework's OpenAIChatClient uses the Responses API (/v1/responses),
which many providers don't support. This client uses the standard Chat Completions
API (/v1/chat/completions) instead.
"""

import asyncio
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


class ChatCompletionsClient:
    """Chat client that uses /v1/chat/completions instead of /v1/responses."""

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

    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send messages to the Chat Completions API and return a ChatResponse."""
        if stream:
            raise NotImplementedError("Streaming not yet supported")

        # Convert AF Messages to OpenAI format
        openai_messages = []
        for msg in messages:
            role = msg.role
            text_parts = []
            tool_calls_list = []

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

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
            max_retries = 3
            last_error: Exception | None = None
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(
                            f"{self._base_url}/chat/completions",
                            json=payload,
                            headers=headers,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        break
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    if status in (429, 502, 503) and attempt < max_retries - 1:
                        last_error = e
                        logger.warning(f"Server error {status} on attempt {attempt + 1}/{max_retries}, retrying...")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
                except (
                    httpx.ReadTimeout,
                    httpx.ConnectTimeout,
                    httpx.ConnectError,
                    httpx.RemoteProtocolError,
                ) as e:
                    last_error = e
                    logger.warning(f"Transient error on attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = e.response.text
            if status == 401 or status == 403:
                raise ChatClientInvalidAuthException(
                    f"Authentication failed ({status}): {body}"
                )
            if status == 400 and "content_filter" in body:
                raise ChatClientContentFilterException(
                    f"Content filter triggered: {body}"
                )
            raise ChatClientException(
                f"Chat Completions API error ({status}): {body}"
            )
        except httpx.RequestError as e:
            raise ChatClientException(f"Request failed: {e}")

        # Parse response
        choice = data["choices"][0]
        msg_data = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        assistant_content = []
        tool_calls_raw = msg_data.get("tool_calls", [])

        if msg_data.get("content"):
            assistant_content.append(msg_data["content"])

        # Build AF Message
        response_msg = Message(
            role="assistant",
            contents=assistant_content,
        )

        # Handle tool calls if present
        if tool_calls_raw:
            for tc in tool_calls_raw:
                fc = Content.from_function_call(
                    call_id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                assistant_content.append(fc)

        usage = data.get("usage", {})
        usage_details = None
        if usage:
            from agent_framework import UsageDetails
            usage_details = UsageDetails(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

        return ChatResponse(
            messages=[response_msg],
            finish_reason=finish_reason,
            model=data.get("model", self._model),
            usage_details=usage_details,
        )
