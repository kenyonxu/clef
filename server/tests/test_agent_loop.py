"""Tests for the agentic tool-use loop."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_framework import Content, Message

from clef_server.agent_loop import AgentLoopResult, run_agent_loop


def _make_response(contents, tool_calls_content=None, finish_reason="stop"):
    """Build a mock ChatResponse.

    Args:
        contents: Text content items for the assistant message.
        tool_calls_content: Optional list of Content(type="function_call") items.
        finish_reason: The finish reason from the LLM.
    """
    all_contents = []
    if contents:
        all_contents.extend(contents)
    if tool_calls_content:
        all_contents.extend(tool_calls_content)

    msg = Message(role="assistant", contents=all_contents)
    mock_resp = MagicMock()
    mock_resp.messages = [msg]
    mock_resp.finish_reason = finish_reason
    return mock_resp


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def echo_tool_executor():
    def executor(call: dict) -> dict:
        return {"echo": call["arguments"], "tool": call["name"]}

    return executor


# -- Tests --


@pytest.mark.asyncio
async def test_single_turn_no_tools(mock_client):
    mock_client.get_response.return_value = _make_response(
        ["Hello, here is your ABC: X:1"]
    )

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose a melody.",
    )

    assert isinstance(result, AgentLoopResult)
    assert result.text == "Hello, here is your ABC: X:1"
    assert result.tool_calls_count == 0
    assert result.turns_used == 1


@pytest.mark.asyncio
async def test_tool_call_then_final_response(mock_client, echo_tool_executor):
    tool_schema = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]

    fc = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "plan.json"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Let me read the file."], tool_calls_content=[fc]),
        _make_response(["Here is the ABC: X:1\nT:Test"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose based on plan.",
        tools=tool_schema,
        tool_executor=echo_tool_executor,
    )

    assert "ABC: X:1" in result.text
    assert result.tool_calls_count == 1
    assert result.turns_used == 2


@pytest.mark.asyncio
async def test_max_turns_limit(mock_client, echo_tool_executor):
    fc = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "plan.json"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Reading..."], tool_calls_content=[fc]),
        _make_response(["Reading again..."], tool_calls_content=[fc]),
        _make_response(["Final output"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                },
            }
        ],
        tool_executor=echo_tool_executor,
        max_turns=2,
    )

    assert result.turns_used == 3  # 2 tool turns + 1 final
    assert result.tool_calls_count == 2


@pytest.mark.asyncio
async def test_tool_execution_error(mock_client):
    def failing_executor(call):
        raise ValueError("File not found: plan.json")

    fc = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "missing.json"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Let me read..."], tool_calls_content=[fc]),
        _make_response(["File not found, but here's my attempt: X:1"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                },
            }
        ],
        tool_executor=failing_executor,
    )

    assert "X:1" in result.text
    assert result.tool_calls_count == 1


@pytest.mark.asyncio
async def test_empty_response(mock_client):
    mock_resp = MagicMock()
    mock_resp.messages = []
    mock_client.get_response.return_value = mock_resp

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
    )

    assert result.text == ""
    assert result.turns_used == 1


@pytest.mark.asyncio
async def test_cancel_check(mock_client):
    """Cancel on turn 1 — the first call to cancel_check returns True."""
    mock_client.get_response.return_value = _make_response(["Hello"])

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        cancel_check=lambda: True,
    )

    assert result.text == ""
    assert result.turns_used == 1


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_one_turn(mock_client, echo_tool_executor):
    fc1 = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "plan.json"}',
    )
    fc2 = Content.from_function_call(
        call_id="call_2",
        name="read_file",
        arguments='{"path": "score.abc"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Reading files..."], tool_calls_content=[fc1, fc2]),
        _make_response(["Here is the merged ABC: X:1\nT:Test"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                },
            }
        ],
        tool_executor=echo_tool_executor,
    )

    assert "ABC: X:1" in result.text
    assert result.tool_calls_count == 2
    assert result.turns_used == 2
