"""
SQL agent — agentic loop.
"""

import os

import anthropic
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


def run_agent(question: str, max_steps: int = 10) -> str:
    messages = [{"role": "user", "content": question}]
    step = 0
    while step < max_steps:
        step += 1

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        print(f"\n[Turn {step}]")

        for block in response.content:
            if block.type == "text" and response.stop_reason == "tool_use":
                print(f"  Claude: {block.text}")
            elif block.type == "tool_use":
                print(f"  Tool  : {block.name}")
                if block.input:
                    for key, val in block.input.items():
                        print(f"  Input : {key} = {val}")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            for block in reversed(response.content):
                if block.type == "text":
                    return block.text
            return ""

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            fn = TOOL_MAP.get(block.name)
            if fn is None:
                result = f"ERROR: unknown tool '{block.name}'"
                print(f"  Error : {result}")
            else:
                try:
                    result = fn(**block.input)
                except Exception as e:
                    result = f"ERROR: {e}"
                    print(f"  Error : {e}")
                else:
                    print(f"  Result: {result[:300]}{'...' if len(result) > 300 else ''}")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return f"Error: agent did not complete within {max_steps} steps."
