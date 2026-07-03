"""
SQL agent — agentic loop.
"""

import os
import json
from dataclasses import dataclass
from typing import Callable

import anthropic
import backoff
from dotenv import load_dotenv

from tools import TOOLS, TOOL_MAP

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM = """You are a data analyst with access to a DuckDB e-commerce warehouse.
The warehouse contains three tables: customers, products, and orders.

To answer questions:
1. Use get_schema to understand the available tables and columns.
2. Use profile_table when you need to explore a table's contents before writing SQL.
3. Use run_sql to execute queries and retrieve data.
4. Reason over the results and give a clear, concise answer.

Always prefer precise SQL over guessing. If a query returns an error, fix it and retry.
"""


@dataclass
class AgentResult:
    final_answer: str
    sql_queries: list[str]
    steps: int
    last_stop_reason: str
    error: str | None = None


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" if line else "" for line in text.splitlines())


def _format_agent_turn(step: int, content) -> str:
    lines = [f"=== Agent turn {step} ==="]
    for block in content:
        if block.type == "text" and block.text.strip():
            lines.extend(["", "Assistant:", _indent(block.text.strip())])
        elif block.type == "tool_use":
            tool_input = json.dumps(block.input, indent=2, sort_keys=True)
            lines.extend([
                "",
                "Tool call:",
                f"  name: {block.name}",
                "  input:",
                _indent(tool_input),
            ])
    return "\n".join(lines) + "\n"


@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def _create_message(messages):
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM,
        tools=TOOLS,
        messages=messages,
    )


def run_agent(
    question: str,
    max_steps: int = 10,
    log_turns: bool = False,
    logger: Callable[[str], None] = print,
) -> AgentResult:
    messages = [{"role": "user", "content": question}]
    step = 0
    sql_queries: list[str] = []

    while step < max_steps:
        step += 1

        try:
            response = _create_message(messages)
        except Exception as e:
            error_msg = f"ERROR: model call failed after retries: {e}"
            return AgentResult(
                final_answer=error_msg,
                sql_queries=sql_queries,
                steps=step,
                last_stop_reason="error",
                error=str(e),
            )

        messages.append({"role": "assistant", "content": response.content})
        if log_turns:
            logger(_format_agent_turn(step, response.content))
        # This simple agent keeps full history. For short SQL tasks that's fine,
        # but a longer-running agent would need context compaction here.

        if response.stop_reason != "tool_use":
            if response.stop_reason == "max_tokens":
                partial_text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return AgentResult(
                    final_answer=(
                        "ERROR: model hit max_tokens before finishing. "
                        f"Partial response:\n{partial_text}"
                    ),
                    sql_queries=sql_queries,
                    steps=step,
                    last_stop_reason=response.stop_reason,
                    error="max_tokens reached",
                )
            return AgentResult(
                final_answer="".join(
                    block.text for block in response.content if block.type == "text"
                ),
                sql_queries=sql_queries,
                steps=step,
                last_stop_reason=response.stop_reason,
            )

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "run_sql" and "query" in block.input:
                sql_queries.append(block.input["query"])

            fn = TOOL_MAP.get(block.name)
            if fn is None:
                result = f"ERROR: unknown tool '{block.name}'"
            else:
                try:
                    result = fn(**block.input)
                except Exception as e:
                    result = f"ERROR: {e}"
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    error_msg = f"Error: agent did not complete within {max_steps} steps."
    return AgentResult(
        final_answer=error_msg,
        sql_queries=sql_queries,
        steps=step,
        last_stop_reason="max_steps",
        error=error_msg,
    )
