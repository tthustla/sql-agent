# Eval Harness

End-to-end evaluation of the text-to-SQL agent against a fixed set of cases.

## Structure

```
evals/
├── cases.py        — EvalCase dataclass + 20-case evaluation suite
├── runner.py       — runs run_agent() over all cases, collects AgentResult pairs
├── scorers.py      — execution accuracy and LLM judge scoring functions
├── report.py       — prints summary/details, saves JSON to evals/results/
├── run_evals.py    — entry point: runner → scorers → report
└── results/        — timestamped JSON output files (gitignored except .gitkeep)
```

## Running

```bash
python evals/run_evals.py
```

By default, the report prints each case header and final answer, then shows
summary accuracy plus scoring details only for execution failures, judge
`partial` verdicts, and judge `incorrect` verdicts.

To show scoring details for every case:

```bash
python evals/run_evals.py --show-all-details
```

## Case coverage

The 20-case suite covers:
- Simple lookups, including multi-column selects
- Scalar aggregations, including decimal averages
- Multi-hop joins
- Date range filters
- NULL handling
- Aggregations with HAVING
- Unanswerable variants where the agent should decline to query

## Scoring signals

| Signal | What it measures | When to trust it |
|---|---|---|
| `exec_accurate` | Did the agent's last SQL return the same rows as gold SQL? | Strong for numeric/lookup; requires valid gold SQL |
| `judge.verdict` | Does the natural-language answer match the gold answer? | Good for unanswerable cases and wording differences; non-deterministic |

Execution scoring compares result sets, not SQL text. For answerable cases it
runs both queries against `warehouse.duckdb`, canonicalizes values with `str()`,
and compares either ordered row sequences or unordered row multisets depending
on `case.ordered`. For unanswerable cases, execution passes only when the agent
does not run SQL.

The summary includes execution accuracy, LLM judge accuracy, and an overall
accuracy that combines both scored signals. The saved JSON also includes
per-case scoring details with reasons, compared SQL, compared rows, judge
reasoning, and the agent's final answer.
