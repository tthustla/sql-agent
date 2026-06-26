# Eval Harness

End-to-end evaluation of the text-to-SQL agent against a fixed set of cases.

## Structure

```
evals/
├── cases.py        — EvalCase dataclass + 20-case evaluation suite
├── runner.py       — runs run_agent() over all cases, collects AgentResult pairs
├── scorers.py      — YOUR CODE: execution_accuracy() and llm_judge() stubs
├── report.py       — prints summary table, saves JSON to evals/results/
├── run_evals.py    — entry point: runner → scorers → report
└── results/        — timestamped JSON output files (gitignored except .gitkeep)
```

## Running

```bash
python evals/run_evals.py
```

The harness runs even with unimplemented scorers — they show as `—` in the report.

## Your job

### 1. Implement the scorers in `scorers.py`

Both functions have detailed docstrings explaining exactly what to build:

**`execution_accuracy(case, result, db_path) -> bool`**
- Execute `case.gold_sql` and the agent's last SQL against DuckDB
- Compare result sets (multiset if `case.ordered=False`, ordered otherwise)
- Return `False` for unanswerable cases where the agent still queried

**`llm_judge(case, result) -> dict`**
- Call `claude-haiku-4-5` with a grading prompt
- Return `{"verdict": "correct"|"partial"|"incorrect", "reason": "..."}`
- Parse robustly (strip code fences before `json.loads`)

### 2. Case coverage in `cases.py`

The 20-case suite covers:
- Multi-hop joins
- Date range filters
- NULL handling
- Aggregations with HAVING
- Ambiguous phrasings
- More unanswerable variants

## Scoring signals

| Signal | What it measures | When to trust it |
|---|---|---|
| `exec_accurate` | Did the agent's SQL return the same rows as gold SQL? | Strong for numeric/lookup; requires valid gold SQL |
| `judge.verdict` | Does the natural-language answer match the gold answer? | Good for unanswerable cases; non-deterministic |

Use both together — execution accuracy can miss paraphrases, and the judge can be fooled by confident-sounding wrong answers.
