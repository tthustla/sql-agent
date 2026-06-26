"""
Entry point for the eval harness.

Usage:
    python evals/run_evals.py
    python evals/run_evals.py --show-all-details
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from runner import run_all
from scorers import execution_accuracy_details, llm_judge
import report

DB_PATH = Path(__file__).parent.parent / "warehouse.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SQL agent evaluation suite.")
    parser.add_argument(
        "--show-all-details",
        action="store_true",
        help="Show scoring details for every case instead of non-passing scores only.",
    )
    return parser.parse_args()


def score_case(case, result) -> dict:
    ea = None
    exec_detail = None
    try:
        exec_detail = execution_accuracy_details(case, result, DB_PATH)
        ea = exec_detail["passed"]
    except NotImplementedError:
        pass
    except Exception as e:
        print(f"  [exec_accuracy error] {e}")

    judge = None
    try:
        judge = llm_judge(case, result)
    except NotImplementedError:
        pass
    except Exception as e:
        print(f"  [llm_judge error] {e}")

    return {"exec_accurate": ea, "exec_detail": exec_detail, "judge": judge}


def main() -> None:
    args = parse_args()
    pairs = run_all()
    scores = [score_case(case, result) for case, result in pairs]
    report.render(pairs, scores, show_all_details=args.show_all_details)


if __name__ == "__main__":
    main()
