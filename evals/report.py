"""
Renders eval results to stdout and saves a JSON file to evals/results/.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _preview(value, limit: int = 500) -> str:
    text = repr(value)
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def render(
    pairs: list[tuple],
    scores: list[dict],
    show_all_details: bool = False,
) -> None:
    """
    Print a summary report and save results to evals/results/<timestamp>.json.

    pairs  — list of (EvalCase, AgentResult) from runner.run_all()
    scores — parallel list of score dicts, one per case:
             {
               "exec_accurate": bool | None,   # None = unscored
               "exec_detail": dict | None,     # comparison context for execution score
               "judge": dict | None,           # None = unscored; e.g. {"verdict": "correct", "reason": "..."}
             }
    show_all_details — show details for every case; otherwise show only cases
                       with execution FAIL or judge verdict "partial"/"incorrect"
    """
    assert len(pairs) == len(scores), "pairs and scores must be the same length"

    n = len(pairs)
    exec_scores = [s["exec_accurate"] for s in scores if s["exec_accurate"] is not None]
    judge_scores = [s["judge"] for s in scores if s["judge"] is not None]

    exec_pct = (sum(exec_scores) / len(exec_scores) * 100) if exec_scores else None
    judge_correct = 0
    verdict_counts: dict[str, int] = {}
    for j in judge_scores:
        v = j.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        if v == "correct":
            judge_correct += 1
    judge_pct = (judge_correct / len(judge_scores) * 100) if judge_scores else None

    total_correct = sum(exec_scores) + judge_correct
    total_scored = len(exec_scores) + len(judge_scores)
    overall_pct = (total_correct / total_scored * 100) if total_scored else None

    print("\n" + "=" * 70)
    print("EVAL REPORT")
    print("=" * 70)

    if exec_pct is not None:
        print(f"Execution accuracy : {exec_pct:.1f}%  ({sum(exec_scores)}/{len(exec_scores)} cases)")
    else:
        print("Execution accuracy : unscored")

    if verdict_counts:
        print(
            f"LLM judge accuracy : {judge_pct:.1f}%  "
            f"({judge_correct}/{len(judge_scores)} correct)"
        )
    else:
        print("LLM judge accuracy : unscored")

    if overall_pct is not None:
        print(
            f"Overall accuracy   : {overall_pct:.1f}%  "
            f"({total_correct}/{total_scored} scored signals)"
        )
    else:
        print("Overall accuracy   : unscored")

    print()
    print(f"{'ID':<20} {'CATEGORY':<14} {'EXEC':>5}  {'JUDGE':<10}  FINAL ANSWER (truncated)")
    print("-" * 80)

    rows = []
    for (case, result), score in zip(pairs, scores):
        ea = score["exec_accurate"]
        j = score["judge"]
        exec_str = "PASS" if ea is True else ("FAIL" if ea is False else "—")
        judge_str = j.get("verdict", "—") if j else "—"
        answer_preview = result.final_answer.replace("\n", " ")[:45]
        if len(result.final_answer) > 45:
            answer_preview += "…"
        print(f"{case.id:<20} {case.category:<14} {exec_str:>5}  {judge_str:<10}  {answer_preview}")
        rows.append({
            "id": case.id,
            "category": case.category,
            "question": case.question,
            "gold_answer": case.gold_answer,
            "final_answer": result.final_answer,
            "sql_queries": result.sql_queries,
            "steps": result.steps,
            "last_stop_reason": result.last_stop_reason,
            "error": result.error,
            "exec_accurate": ea,
            "exec_detail": score.get("exec_detail"),
            "judge": j,
        })

    detail_cases = [
        ((case, result), score)
        for (case, result), score in zip(pairs, scores)
        if show_all_details
        or score["exec_accurate"] is False
        or (
            score["judge"] is not None
            and score["judge"].get("verdict") in {"partial", "incorrect"}
        )
    ]

    print()
    print(
        "SCORING DETAILS"
        + (" (all cases)" if show_all_details else " (non-passing scores only)")
    )
    print("-" * 80)
    if not detail_cases:
        print("No failed, partial, or incorrect scores.")
        print()

    for (case, result), score in detail_cases:
        detail = score.get("exec_detail")
        judge = score["judge"]
        exec_str = "PASS" if score["exec_accurate"] is True else (
            "FAIL" if score["exec_accurate"] is False else "—"
        )
        judge_str = judge.get("verdict", "—") if judge else "—"

        print(f"{case.id}")
        if detail:
            print(f"  EXEC {exec_str}: {detail.get('reason', '')}")
            print(f"    gold_sql : {detail.get('gold_sql')}")
            print(f"    agent_sql: {detail.get('agent_sql')}")
            print(f"    gold_rows : {_preview(detail.get('gold_rows'))}")
            print(f"    agent_rows: {_preview(detail.get('agent_rows'))}")
        else:
            print(f"  EXEC {exec_str}: no execution details available")

        if judge:
            print(f"  JUDGE {judge_str}: {judge.get('reason', '')}")
            print(f"    reference answer: {_preview(case.gold_answer)}")
            print(f"    agent answer    : {_preview(result.final_answer)}")
        else:
            print(f"  JUDGE {judge_str}: no judge details available")
        print()

    print("=" * 70)

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = results_dir / f"eval_{ts}.json"

    summary = {
        "timestamp": ts,
        "n_cases": n,
        "exec_accuracy_pct": exec_pct,
        "judge_accuracy_pct": judge_pct,
        "overall_accuracy_pct": overall_pct,
        "judge_verdict_counts": verdict_counts,
        "cases": rows,
    }
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nResults saved to {out_path.relative_to(Path(__file__).parent.parent)}")
