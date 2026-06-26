from pathlib import Path
import json
import re

import duckdb


VALID_VERDICTS = {"correct", "partial", "incorrect"}


def _canonical_row(row: tuple) -> tuple[str, ...]:
    return tuple("" if value is None else str(value) for value in row)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _fetch_rows(conn, query: str) -> list[tuple]:
    return conn.execute(query).fetchall()


def execution_accuracy(case, result, db_path: str | Path) -> bool | None:
    """
    Return whether the agent's final SQL result matches the gold SQL result.

    The scorer uses result.sql_queries[-1] as the agent's answer query. For
    answerable cases, it executes both that query and case.gold_sql against the
    same DuckDB database, canonicalizes each value with str(), and compares the
    resulting rows. Ordered cases require exact row sequence equality; unordered
    cases compare sorted row multisets.

    Unanswerable cases are handled without executing SQL: they pass when
    case.gold_sql is None and the agent did not run any SQL, and fail if the
    agent queried anyway. Any SQL or DuckDB exception is scored as False.

    Use execution_accuracy_details() when the report needs the reason, SQL, and
    compared row sets in addition to the boolean score.
    """
    return execution_accuracy_details(case, result, db_path)["passed"]


def execution_accuracy_details(case, result, db_path: str | Path) -> dict:
    """
    Return execution accuracy plus context explaining the result.

    The returned dict includes:
      - passed: bool score
      - reason: one-sentence explanation for pass/fail
      - gold_sql / agent_sql: queries used for comparison, when available
      - gold_rows / agent_rows: canonicalized fetched rows, when executed
    """
    detail = {
        "passed": None,
        "reason": "",
        "gold_sql": case.gold_sql,
        "agent_sql": result.sql_queries[-1] if result.sql_queries else None,
        "gold_rows": None,
        "agent_rows": None,
    }

    if case.gold_sql is None:
        if result.sql_queries:
            detail["passed"] = False
            detail["reason"] = (
                "Case is unanswerable, but the agent ran SQL when it should "
                "have declined."
            )
        else:
            detail["passed"] = True
            detail["reason"] = (
                "Case is unanswerable and the agent did not run SQL."
            )
        return detail

    if not result.sql_queries:
        detail["passed"] = False
        detail["reason"] = "Case is answerable, but the agent did not run SQL."
        return detail

    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            gold_rows = _fetch_rows(conn, case.gold_sql)
            agent_rows = _fetch_rows(conn, detail["agent_sql"])
        finally:
            conn.close()
    except Exception as exc:
        detail["passed"] = False
        detail["reason"] = f"SQL execution failed: {exc}"
        return detail

    gold_rows = [_canonical_row(row) for row in gold_rows]
    agent_rows = [_canonical_row(row) for row in agent_rows]
    detail["gold_rows"] = gold_rows
    detail["agent_rows"] = agent_rows

    if case.ordered:
        passed = gold_rows == agent_rows
        comparison = "ordered row sequence"
    else:
        passed = sorted(gold_rows) == sorted(agent_rows)
        comparison = "unordered row multiset"

    detail["passed"] = passed
    if passed:
        detail["reason"] = f"Gold and agent results match as an {comparison}."
    else:
        detail["reason"] = (
            f"Gold and agent results differ when compared as an {comparison}."
        )

    return detail


def llm_judge(case, result) -> dict:
    """
    Grade the final natural-language answer against the reference answer.

    The judge sends the original question, case.gold_answer, and
    result.final_answer to claude-haiku-4-5 and asks for strict JSON with:
      {"verdict": "correct"|"partial"|"incorrect", "reason": "..."}

    Markdown JSON fences are stripped before parsing. Malformed JSON, unknown
    verdicts, or missing string reasons return {"verdict": "error", ...} so the
    report can surface the grading failure without crashing the eval run.

    This is a soft, non-deterministic scoring signal. It complements
    execution_accuracy, especially for unanswerable cases and harmless wording
    differences in final answers.
    """
    import anthropic

    prompt = f"""
You are grading a text-to-SQL agent's final answer.

Compare the agent answer to the reference answer for the original question.
Grade semantic correctness, allowing harmless wording differences.

Original question:
{case.question}

Reference answer:
{case.gold_answer}

Agent final answer:
{result.final_answer}

Return STRICT JSON ONLY with this exact schema and no prose outside the JSON:
{{"verdict": "correct"|"partial"|"incorrect", "reason": "<one sentence>"}}
""".strip()

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    stripped = _strip_code_fence(raw)

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"verdict": "error", "reason": raw}

    verdict = parsed.get("verdict")
    reason = parsed.get("reason")
    if verdict not in VALID_VERDICTS or not isinstance(reason, str):
        return {"verdict": "error", "reason": stripped}

    return {"verdict": verdict, "reason": reason}
