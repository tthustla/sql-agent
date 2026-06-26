"""
Runs the agent over all eval cases and collects results.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent import AgentResult, run_agent
from cases import CASES, EvalCase


def run_all(max_steps: int = 10) -> list[tuple[EvalCase, AgentResult]]:
    pairs: list[tuple[EvalCase, AgentResult]] = []
    for case in CASES:
        print(f"\n{'=' * 60}")
        print(f"Case: {case.id}  [{case.category}]")
        print(f"Q: {case.question}")
        print("=" * 60)
        try:
            result = run_agent(case.question, max_steps=max_steps)
        except Exception as e:
            result = AgentResult(
                final_answer=f"ERROR: {e}",
                sql_queries=[],
                steps=0,
                last_stop_reason="error",
                error=str(e),
            )
        print("\nFinal answer:")
        print(result.final_answer)
        pairs.append((case, result))
    return pairs
