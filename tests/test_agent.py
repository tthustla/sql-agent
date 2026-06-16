"""
Tests for src/agent.py — specifically the run_agent() loop logic.

The Anthropic client and TOOL_MAP are both mocked so no real API calls
or database queries are made. These tests verify control flow only.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import agent


# ── Helpers ────────────────────────────────────────────────────────────────────

def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def tool_block(name: str, tool_input: dict, id: str = "toolu_001"):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=tool_input)


def api_response(stop_reason: str, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_end_turn_with_no_tools():
    """Model answers immediately without calling any tools."""
    mock_create = MagicMock(return_value=api_response(
        "end_turn", text_block("The answer is 42.")
    ))
    with patch.object(agent.client.messages, "create", mock_create):
        result = agent.run_agent("What is 6 times 7?")

    assert result == "The answer is 42."
    assert mock_create.call_count == 1


def test_end_turn_concatenates_multiple_text_blocks():
    """Final answers include all text blocks from the last model turn."""
    mock_create = MagicMock(return_value=api_response(
        "end_turn", text_block("Part one. "), text_block("Part two.")
    ))

    with patch.object(agent.client.messages, "create", mock_create):
        result = agent.run_agent("Give me a two-part answer.")

    assert result == "Part one. Part two."


def test_model_call_retries_after_transient_failure():
    """A transient model-call error is retried by the backoff wrapper."""
    mock_create = MagicMock(side_effect=[
        RuntimeError("temporary outage"),
        api_response("end_turn", text_block("Recovered answer.")),
    ])

    with patch.object(agent.client.messages, "create", mock_create), \
         patch("backoff._sync.time.sleep") as mock_sleep:
        result = agent.run_agent("Try again.")

    assert result == "Recovered answer."
    assert mock_create.call_count == 2
    mock_sleep.assert_called_once()


def test_single_tool_call_then_end_turn():
    """Model makes one tool call, gets the result, then gives a final answer."""
    mock_create = MagicMock(side_effect=[
        api_response("tool_use", text_block("Let me check."), tool_block("get_schema", {})),
        api_response("end_turn", text_block("There are 3 tables.")),
    ])
    mock_tool = MagicMock(return_value="Table: customers\nTable: orders")

    with patch.object(agent.client.messages, "create", mock_create), \
         patch.dict(agent.TOOL_MAP, {"get_schema": mock_tool}):
        result = agent.run_agent("What tables exist?")

    assert result == "There are 3 tables."
    assert mock_create.call_count == 2
    mock_tool.assert_called_once_with()


def test_tool_input_passed_correctly():
    """run_agent passes block.input as kwargs to the tool function."""
    mock_create = MagicMock(side_effect=[
        api_response("tool_use", tool_block("run_sql", {"query": "SELECT 1"})),
        api_response("end_turn", text_block("Done.")),
    ])
    mock_tool = MagicMock(return_value="1")

    with patch.object(agent.client.messages, "create", mock_create), \
         patch.dict(agent.TOOL_MAP, {"run_sql": mock_tool}):
        agent.run_agent("Run a query.")

    mock_tool.assert_called_once_with(query="SELECT 1")


def test_multiple_tool_calls_in_one_turn():
    """Model requests two tools in a single turn; both results go in one user message."""
    mock_create = MagicMock(side_effect=[
        api_response(
            "tool_use",
            tool_block("get_schema", {}, id="toolu_001"),
            tool_block("profile_table", {"table": "orders"}, id="toolu_002"),
        ),
        api_response("end_turn", text_block("Got it.")),
    ])
    mock_schema  = MagicMock(return_value="schema text")
    mock_profile = MagicMock(return_value="profile text")

    with patch.object(agent.client.messages, "create", mock_create), \
         patch.dict(agent.TOOL_MAP, {"get_schema": mock_schema, "profile_table": mock_profile}):
        result = agent.run_agent("Describe the data.")

    # Both tools should have been called
    mock_schema.assert_called_once()
    mock_profile.assert_called_once_with(table="orders")

    # The second API call's messages should contain both tool results in one user turn.
    # Use [-2] because agent.py appends the second assistant turn to the same list
    # object after the call, making [-1] the assistant turn by the time we read it.
    second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_result_turn = second_call_messages[-2]
    assert tool_result_turn["role"] == "user"
    assert len(tool_result_turn["content"]) == 2


def test_max_tokens_returns_error_with_partial_text():
    """A max_tokens stop reason returns an explicit error and partial answer text."""
    mock_create = MagicMock(return_value=api_response(
        "max_tokens", text_block("Partial "), text_block("answer")
    ))

    with patch.object(agent.client.messages, "create", mock_create):
        result = agent.run_agent("Give me a very long answer.")

    assert result == "ERROR: model hit max_tokens before finishing. Partial response:\nPartial answer"


def test_max_steps_exceeded():
    """Loop returns an error string when max_steps is hit without end_turn."""
    mock_create = MagicMock(return_value=api_response(
        "tool_use", tool_block("get_schema", {})
    ))
    mock_tool = MagicMock(return_value="schema")

    with patch.object(agent.client.messages, "create", mock_create), \
         patch.dict(agent.TOOL_MAP, {"get_schema": mock_tool}):
        result = agent.run_agent("Loop forever.", max_steps=3)

    assert "Error" in result
    assert "3" in result
    assert mock_create.call_count == 3


def test_unknown_tool_name_does_not_crash():
    """An unrecognised tool name returns an error string to the model instead of raising."""
    mock_create = MagicMock(side_effect=[
        api_response("tool_use", tool_block("nonexistent_tool", {}, id="toolu_x")),
        api_response("end_turn", text_block("Recovered.")),
    ])

    with patch.object(agent.client.messages, "create", mock_create):
        result = agent.run_agent("Use a fake tool.")

    assert result == "Recovered."
    # Use [-2]: agent.py appends the end_turn assistant turn after the second call,
    # so [-1] is that assistant turn and [-2] is the tool_result user turn.
    second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_result_content = second_call_messages[-2]["content"][0]["content"]
    assert "unknown tool" in tool_result_content


def test_tool_exception_is_caught():
    """An exception raised inside a tool is caught and returned as an error string."""
    mock_create = MagicMock(side_effect=[
        api_response("tool_use", tool_block("run_sql", {"query": "SELECT 1"}, id="toolu_y")),
        api_response("end_turn", text_block("Handled.")),
    ])
    mock_tool = MagicMock(side_effect=RuntimeError("db exploded"))

    with patch.object(agent.client.messages, "create", mock_create), \
         patch.dict(agent.TOOL_MAP, {"run_sql": mock_tool}):
        result = agent.run_agent("Run a bad query.")

    assert result == "Handled."
    second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_result_content = second_call_messages[-2]["content"][0]["content"]
    assert "db exploded" in tool_result_content


def test_messages_accumulate_correctly():
    """After one tool round-trip, messages has: user, assistant, user(tool_result)."""
    mock_create = MagicMock(side_effect=[
        api_response("tool_use", tool_block("get_schema", {})),
        api_response("end_turn", text_block("Done.")),
    ])
    mock_tool = MagicMock(return_value="schema")

    captured = {}

    def capture_create(**kwargs):
        captured["last_messages"] = kwargs["messages"]
        return mock_create(**kwargs)

    with patch.object(agent.client.messages, "create", mock_create), \
         patch.dict(agent.TOOL_MAP, {"get_schema": mock_tool}):
        agent.run_agent("What is the schema?")

    # messages is a mutable list; agent.py appends the final assistant turn after
    # the second call, so we check only the first 3 entries (the state at call time).
    final_messages = mock_create.call_args_list[1].kwargs["messages"]
    roles = [m["role"] for m in final_messages]
    assert roles[:3] == ["user", "assistant", "user"]
