# sql-agent

A text-to-SQL agent over a local DuckDB warehouse, built as portfolio project 1 of a series.

The agent uses the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) with tool use to answer natural-language questions about an e-commerce dataset. It demonstrates how an **agentic loop** works: a model that repeatedly calls tools, observes results, and decides what to do next until it can give a final answer.

The loop also includes a few production-minded guardrails: batched tool-result turns for parallel tool calls, automatic retry/backoff around model requests, and explicit handling for incomplete `max_tokens` responses.

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
```

Example output:

```
The Electronics category had the most revenue at $14,398.20.
```

If the model exhausts its output budget, the agent returns an explicit error with the partial response instead of treating it as a completed answer.

The CLI prints only the final answer. Tool calls and intermediate model turns
are captured internally in `AgentResult` for tests/evals, but are not logged for
normal use.

---

## Running tests

```bash
# Install dev dependencies (adds pytest)
pip install -r requirements-dev.txt

# Run the full suite
pytest tests/ -v
```

Tests use an isolated in-memory DuckDB fixture — the real `warehouse.duckdb` is never touched.

---

## Running evals

```bash
python evals/run_evals.py
python evals/run_evals.py --show-all-details
```

The eval harness runs the agent against 20 fixed cases, prints each final
answer, and reports execution accuracy, LLM judge accuracy, and combined
overall accuracy. By default, detailed scoring comparisons are shown only for
execution failures and judge `partial`/`incorrect` verdicts; use
`--show-all-details` to inspect every case.

---

## Warehouse schema

| Table | Columns |
|-------|---------|
| `customers` | id, name, country, signup_date |
| `products` | id, name, category, price |
| `orders` | id, customer_id, product_id, quantity, order_date |

~500 orders across ~12 months (July 2024 – June 2025), weighted toward recent months so trend queries return interesting results.
