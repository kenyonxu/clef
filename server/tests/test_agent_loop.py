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
async def test_max_turns_final_response_filters_function_calls(mock_client, echo_tool_executor):
    """When max_turns is reached, function_call Content items in the final
    response must be filtered out — they should NOT appear in result.text."""
    fc = Content.from_function_call(
        call_id="call_1",
        name="write_file",
        arguments='{"path": "score.abc", "content": "V:1\\nc2 d2 |"}',
    )

    mock_client.get_response.side_effect = [
        # Turn 1: tool call (consumes turn)
        _make_response(["Writing..."], tool_calls_content=[fc]),
        # Turn 2: tool call again (consumes turn, max_turns=2 reached)
        _make_response(["Writing more..."], tool_calls_content=[fc]),
        # Forced final response: contains BOTH text AND a function_call
        _make_response(
            ["Here is my ABC"],
            tool_calls_content=[Content.from_function_call(
                call_id="call_2",
                name="validate_abc",
                arguments='{"abc": "V:1\\nc2 d2 |"}',
            )],
        ),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[{"type": "function", "function": {"name": "write_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}}],
        tool_executor=echo_tool_executor,
        max_turns=2,
    )

    # Text should contain the actual text response, NOT "Content(type=function_call)"
    assert "Content(type=" not in result.text
    assert "Here is my ABC" in result.text
    assert result.turns_used == 3  # 2 tool turns + 1 final
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


# -- Layer 3: DEDUP turn budget tests --


@pytest.mark.asyncio
async def test_dedup_tool_calls_dont_count_as_turn(mock_client):
    """All-DEDUP turn should NOT consume turn budget, allowing real calls to proceed.

    With max_turns=1: old code would exhaust the budget on the DEDUP turn and skip
    the real write call. New code skips DEDUP turn, executes real call, then final.
    """
    def dedup_executor(call):
        """Returns _dedup=True for read-only tools, real result for writes."""
        if call["name"] == "write_file":
            return {"written": call["arguments"]["path"]}
        return {"_dedup": True, "data": call["arguments"]}

    dedup_fc = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "plan.json"}',
    )
    real_fc = Content.from_function_call(
        call_id="call_2",
        name="write_file",
        arguments='{"path": "out.abc", "content": "V:1\\nc2 d2 |"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Reading..."], tool_calls_content=[dedup_fc]),  # DEDUP turn
        _make_response(["Writing..."], tool_calls_content=[real_fc]),   # Real turn
        _make_response(["Done: V:1"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "write_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
        ],
        tool_executor=dedup_executor,
        max_turns=1,
    )

    # Critical: old code would only execute 1 tool call (DEDUP) with max_turns=1.
    # New code skips DEDUP turn, executes real write → 2 total tool calls.
    assert result.tool_calls_count == 2  # 1 dedup + 1 real
    assert "Done" in result.text
    assert result.turns_used == 2  # 1 real turn + 1 final


@pytest.mark.asyncio
async def test_mixed_dedup_and_real_counts_as_turn(mock_client):
    """When a mix of DEDUP and real calls exist in one response, count it as a real turn."""
    def mixed_executor(call):
        if call["name"] == "read_file":
            return {"_dedup": True, "data": call["arguments"]}
        return {"data": call["arguments"]}

    dedup_fc = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "plan.json"}',
    )
    real_fc = Content.from_function_call(
        call_id="call_2",
        name="write_file",
        arguments='{"path": "out.txt", "content": "hello"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Mixed..."], tool_calls_content=[dedup_fc, real_fc]),  # 1 dedup + 1 real
        _make_response(["Done"]),
    ]

    result = await run_agent_loop(
        client=mock_client,
        system_prompt="You are a composer.",
        user_message="Compose.",
        tools=[
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "write_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
        ],
        tool_executor=mixed_executor,
        max_turns=2,
    )

    assert result.turns_used == 2  # 1 mixed turn (counted) + 1 final


@pytest.mark.asyncio
async def test_dedup_flag_stripped_from_llm_message(mock_client):
    """_dedup key must not appear in the tool result string sent to LLM.

    Verifies the internal _dedup flag is stripped before serializing to JSON
    for the LLM message, while _dedup_note is preserved for the LLM hint.
    """
    def capturing_executor(call):
        return {"_dedup": True, "_dedup_note": "You already called this.", "data": "hello"}

    fc = Content.from_function_call(
        call_id="call_1",
        name="read_file",
        arguments='{"path": "f.txt"}',
    )

    mock_client.get_response.side_effect = [
        _make_response(["Reading..."], tool_calls_content=[fc]),
        _make_response(["Here's my output"]),
    ]

    await run_agent_loop(
        client=mock_client,
        system_prompt="Test.",
        user_message="Read file.",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}],
        tool_executor=capturing_executor,
        max_turns=3,
    )

    # Verify the tool result message sent to LLM on the 2nd get_response call
    # does NOT contain _dedup key but DOES contain _dedup_note and data.
    second_call_args = mock_client.get_response.call_args_list[1]
    messages = second_call_args[0][0]  # First positional arg is messages list
    # Find the tool message (role="tool")
    tool_msg = [m for m in messages if m.role == "tool"][0]
    result_json = tool_msg.contents[0].result  # type: ignore[attr-defined]
    assert '"_dedup"' not in result_json, f"_dedup leaked to LLM: {result_json}"
    assert '"_dedup_note"' in result_json, "_dedup_note should be preserved for LLM"
    assert '"data"' in result_json, "actual data should be preserved"
