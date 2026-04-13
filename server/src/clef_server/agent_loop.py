"""Agentic tool-use loop — ReAct-style LLM + tool execution cycle.

Each turn:
  1. Send messages to LLM (including tool schemas if any)
  2. Parse response: if function_call contents present, execute them, append results, repeat
  3. If no function_call contents (finish_reason="stop"), return final text
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from agent_framework import Content, Message

logger = logging.getLogger(__name__)


@dataclass
class AgentLoopResult:
    """Result from an agentic loop execution."""

    text: str
    tool_calls_count: int = 0
    turns_used: int = 1


def _extract_tool_calls(message: Message) -> list[Content]:
    """Extract function_call Content items from a Message."""
    if not message.contents:
        return []
    return [c for c in message.contents if hasattr(c, "type") and c.type == "function_call"]


def _extract_text(message: Message) -> str:
    """Extract text content from a Message, skipping function_call/function_result items."""
    if not message.contents:
        return ""
    parts = []
    for c in message.contents:
        if hasattr(c, "type") and c.type in ("function_call", "function_result"):
            continue
        text = c.text if hasattr(c, "text") and c.text else str(c)
        if text:
            parts.append(str(text))
    return "\n".join(parts)


async def run_agent_loop(
    client: Any,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    tool_executor: Any = None,
    *,
    temperature: float = 0.7,
    max_turns: int = 5,
    max_tokens: int = 4096,
    turn_timeout: float = 120.0,
    cancel_check: Any = None,
) -> AgentLoopResult:
    """Run an agentic tool-use loop until the LLM stops calling tools."""
    messages = [
        Message(role="system", contents=[system_prompt]),
        Message(role="user", contents=[user_message]),
    ]

    total_tool_calls = 0
    turns_used = 0

    while turns_used < max_turns:
        if cancel_check and cancel_check():
            logger.info("Agent loop cancelled at turn %d", turns_used + 1)
            return AgentLoopResult(text="", turns_used=turns_used + 1)

        try:
            response = await asyncio.wait_for(
                client.get_response(
                    messages,
                    tools=tools if tools else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=turn_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Agent loop turn %d timed out after %.0fs, returning empty result",
                turns_used + 1, turn_timeout,
            )
            return AgentLoopResult(text="", turns_used=turns_used + 1, tool_calls_count=total_tool_calls)

        if not response.messages:
            return AgentLoopResult(text="", turns_used=turns_used + 1)

        assistant_msg = response.messages[0]
        tool_calls = _extract_tool_calls(assistant_msg)

        if not tool_calls:
            content = _extract_text(assistant_msg)
            return AgentLoopResult(
                text=content,
                tool_calls_count=total_tool_calls,
                turns_used=turns_used + 1,
            )

        total_tool_calls += len(tool_calls)
        messages.append(assistant_msg)

        has_real_call = False
        for tc in tool_calls:
            tool_name = tc.name
            try:
                args = (
                    json.loads(tc.arguments)
                    if isinstance(tc.arguments, str)
                    else (tc.arguments if tc.arguments else {})
                )
            except json.JSONDecodeError:
                args = {}

            logger.info(
                "Agent loop turn %d: calling tool %s with args %s",
                turns_used + 1,
                tool_name,
                json.dumps(args, ensure_ascii=False)[:200],
            )

            if tool_executor:
                try:
                    result = tool_executor({"name": tool_name, "arguments": args})
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})
                    logger.error("Tool %s execution failed: %s", tool_name, e)
                    tool_result = Content.from_function_result(
                        call_id=tc.call_id or "",
                        result=result_str,
                    )
                    tool_msg = Message(role="tool", contents=[tool_result])
                    messages.append(tool_msg)
                    has_real_call = True
                    continue

                # Check for DEDUP cache hit via _dedup flag
                is_dedup = isinstance(result, dict) and result.get("_dedup", False)

                # Strip internal _dedup flag before sending to LLM,
                # but keep _dedup_note so the LLM sees the hint.
                if is_dedup:
                    result = {k: v for k, v in result.items() if k != "_dedup"}

                result_str = (
                    json.dumps(result, ensure_ascii=False)
                    if isinstance(result, dict)
                    else str(result)
                )

                if not is_dedup:
                    has_real_call = True
            else:
                result_str = json.dumps({"error": "No tool executor configured"})
                is_dedup = False
                has_real_call = True

            tool_result = Content.from_function_result(
                call_id=tc.call_id or "",
                result=result_str,
            )
            tool_msg = Message(role="tool", contents=[tool_result])
            messages.append(tool_msg)

        if has_real_call:
            turns_used += 1
            # Rate-limit pacing: brief pause between turns to avoid API 429
            await asyncio.sleep(1)
        else:
            logger.info(
                "Agent loop: all tool calls were DEDUP hits, not counting as a turn"
            )

    logger.warning(
        "Agent loop reached max_turns=%d, requesting final response", max_turns
    )
    response = await client.get_response(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = ""
    if response.messages and response.messages[0].contents:
        content = _extract_text(response.messages[0])

    return AgentLoopResult(
        text=content,
        tool_calls_count=total_tool_calls,
        turns_used=turns_used + 1,
    )
