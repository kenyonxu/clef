"""Agentic tool-use loop — ReAct-style LLM + tool execution cycle.

Each turn:
  1. Send messages to LLM (including tool schemas if any)
  2. Parse response: if function_call contents present, execute them, append results, repeat
  3. If no function_call contents (finish_reason="stop"), return final text
"""

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
    cancel_check: Any = None,
) -> AgentLoopResult:
    """Run an agentic tool-use loop until the LLM stops calling tools."""
    messages = [
        Message(role="system", contents=[system_prompt]),
        Message(role="user", contents=[user_message]),
    ]

    total_tool_calls = 0

    for turn in range(max_turns):
        if cancel_check and cancel_check():
            logger.info("Agent loop cancelled at turn %d", turn + 1)
            return AgentLoopResult(text="", turns_used=turn + 1)

        response = await client.get_response(
            messages,
            tools=tools if tools else None,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if not response.messages:
            return AgentLoopResult(text="", turns_used=turn + 1)

        assistant_msg = response.messages[0]
        tool_calls = _extract_tool_calls(assistant_msg)

        if not tool_calls:
            content = ""
            if assistant_msg.contents:
                content = "\n".join(
                    str(c.text if hasattr(c, "text") and c.text else c)
                    for c in assistant_msg.contents
                )
            return AgentLoopResult(
                text=content,
                tool_calls_count=total_tool_calls,
                turns_used=turn + 1,
            )

        total_tool_calls += len(tool_calls)
        messages.append(assistant_msg)

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
                turn + 1,
                tool_name,
                json.dumps(args, ensure_ascii=False)[:200],
            )

            if tool_executor:
                try:
                    result = tool_executor({"name": tool_name, "arguments": args})
                    result_str = (
                        json.dumps(result, ensure_ascii=False)
                        if isinstance(result, dict)
                        else str(result)
                    )
                except Exception as e:
                    result_str = json.dumps({"error": str(e)})
                    logger.error("Tool %s execution failed: %s", tool_name, e)
            else:
                result_str = json.dumps({"error": "No tool executor configured"})

            tool_result = Content.from_function_result(
                call_id=tc.call_id or "",
                result=result_str,
            )
            tool_msg = Message(role="tool", contents=[tool_result])
            messages.append(tool_msg)

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
        content = "\n".join(
            str(c.text if hasattr(c, "text") and c.text else c)
            for c in response.messages[0].contents
        )

    return AgentLoopResult(
        text=content,
        tool_calls_count=total_tool_calls,
        turns_used=max_turns + 1,
    )
