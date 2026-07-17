# sql-agent

A text-to-SQL agent over a local DuckDB warehouse, built as a portfolio project exploring what it takes to make an AI agent trustworthy in production — not just functional in a demo.

The agent uses the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) with tool use to answer natural-language questions about an e-commerce dataset. It demonstrates how an **agentic loop** works: a model that repeatedly calls tools, observes results, and decides what to do next until it can give a final answer.

Most text-to-SQL demos stop at "the query ran". This project goes further: the agentic loop handles edge cases and failure modes gracefully, an evaluation harness scores answer quality rather than just execution success, and production-minded guardrails are built in throughout. The goal was to understand the gap between a working prototype and something you'd actually trust with real users.

---

## How it works

```
User question
     │
     ▼
┌─────────────────────────────────────────┐
│  agent.py — agentic loop                │
│                                         │
│  while stop_reason == "tool_use":       │
│    1. Call Claude with tools + messages │
│    2. Dispatch tool calls               │
│    3. Batch tool results into one turn  │
│    4. Append results to messages        │
│                                         │
│  return concatenated final text         │
└─────────────────────────────────────────┘
     │                    │
     ▼                    ▼
tools.py            warehouse.duckdb
get_schema()        customers
run_sql()           products
profile_table()     orders
```

---

## Key design decisions

**Batched tool-result turns for parallel tool calls**
When the model requests multiple tools in a single turn, results are batched into one combined message rather than sent back individually. This keeps the message history clean and avoids the model losing context across multiple short turns — a subtle but meaningful reliability improvement at scale.

**Explicit handling for incomplete `max_tokens` responses**
Rather than silently treating a truncated response as a completed answer, the agent detects `stop_reason == "max_tokens"` and returns an explicit error with the partial response. Failing loudly is preferable to returning a confidently wrong answer.

**Automatic retry with backoff**
Model requests wrap a retry/backoff loop to handle transient API errors. This is the kind of thing that gets added in production after the first on-call incident — building it in from the start keeps the loop stable under real conditions.

**Dual-metric evaluation: execution accuracy + LLM judge**
Execution accuracy alone is too coarse — a query can run successfully and still return the wrong answer. The LLM judge catches semantic failures that execution accuracy misses (wrong aggregation, incorrect filter, right shape but wrong values). Using both metrics gives a more honest picture of agent quality.

**DuckDB as the warehouse**
Chosen for zero-infrastructure local development: no running server, no credentials, no setup friction. The synthetic e-commerce dataset (~500 orders, ~12 months) is generated deterministically so results are reproducible across environments.

---

## Project structure

```
sql-agent/
├── data/
│   └── build_db.py          # generates the synthetic warehouse
├── evals/
│   ├── cases.py             # fixed text-to-SQL eval cases
│   ├── scorers.py           # execution accuracy + LLM judge scoring
│   ├── report.py            # stdout/JSON eval reports
│   └── run_evals.py         # eval entry point
├── src/
│   ├── tools.py             # tool implementations + Anthropic schemas
│   ├── agent.py             # agentic loop
│   └── main.py              # CLI entry point
├── tests/
│   ├── conftest.py          # shared fixtures (isolated test DB)
│   ├── test_tools.py        # unit tests for tools.py
│   └── test_agent.py        # unit tests for the agent loop
├── .env.example
├── requirements.txt         # pinned production dependencies
└── requirements-dev.txt     # adds pytest for development
```

---

## Setup

**Prerequisites:** Python 3.8+

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build the warehouse (creates warehouse.duckdb in the project root)
python data/build_db.py

# 4. Add your Anthropic API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

Get an API key at [console.anthropic.com](https://console.anthropic.com) → API Keys.

---

## Usage

```bash
# Ask a question directly
python src/main.py "Which product category had the most revenue?"

# Interactive prompt
python src/main.py

# Override the max tool-call rounds (default: 10)
python src/main.py --max-steps 20 "Give me a detailed breakdown by country and category."

# Show each assistant turn and tool call as the agent runs
python src/main.py --log-turns "Which product category had the most revenue?"
```

Example output:

```
The Electronics category had the most revenue at $14,398.20.
```

If the model exhausts its output budget, the agent returns an explicit error
with the partial response instead of treating it as a completed answer.

The CLI prints only the final answer by default. Pass `--log-turns` to also
show each assistant turn and requested tool call as the agent runs.

---

## Running tests

```bash
# Install dev dependencies (adds pytest)
pip install -r requirements-dev.txt

# Run the full suite
pytest tests/ -v
```

Tests use an isolated in-memory DuckDB fixture — the real `warehouse.duckdb`
is never touched.

---

## Running evals

```bash
python evals/run_evals.py
python evals/run_evals.py --show-all-details
```

The eval harness runs the agent against 20 fixed cases and reports execution
accuracy, LLM judge accuracy, and combined overall accuracy.

Example output:

```
Execution accuracy :  18 / 20  (90%)
LLM judge accuracy :  17 / 20  (85%)
Overall            :  17 / 20  (85%)
```

By default, detailed scoring comparisons are shown only for execution failures
and judge `partial`/`incorrect` verdicts. Use `--show-all-details` to inspect
every case.

---

## Warehouse schema

| Table | Columns |
|-------|---------|
| `customers` | id, name, country, signup_date |
| `products` | id, name, category, price |
| `orders` | id, customer_id, product_id, quantity, order_date |

~500 orders across ~12 months (July 2024 – June 2025), weighted toward recent
months so trend queries return interesting results.

---

## What's next

- **Input guardrails** — validate and sanitise natural-language queries before they reach the model, rejecting clearly out-of-scope or potentially harmful inputs
- **Output hooks** — confidence scoring and result sanity checks on the agent's final answer before it reaches the user
- **Streaming responses** — surface partial answers progressively for a better interactive experience
