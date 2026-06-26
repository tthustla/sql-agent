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
    Compare the agent's last SQL query result set against the gold SQL result set.

    Returns True for an unanswerable case where the agent correctly avoided
    running SQL.

    Implementation notes:
    -------------------------
    1. Take the agent's "answer query" from result.sql_queries.
       Heuristic: use result.sql_queries[-1] (the last query run).
       If result.sql_queries is empty, return False immediately.

    2. If case.gold_sql is None (unanswerable case) but the agent ran any SQL,
       return False — the agent should have declined to query.

    3. Execute case.gold_sql against the DuckDB warehouse at db_path to get
       gold_rows (list of tuples).

    4. Execute result.sql_queries[-1] against the same db_path to get
       agent_rows (list of tuples).

    5. Compare:
       - If case.ordered is False: compare as multisets (sort both, then ==).
         Use sorted(gold_rows) == sorted(agent_rows) after converting rows to
         a canonical form (e.g., tuple of str for each value).
       - If case.ordered is True: compare sequences directly (gold_rows == agent_rows).

    6. Return True if the result sets match, False otherwise.
       Catch any DuckDB or SQL exception and return False.

    Suggested imports:
        import duckdb

    Example:
        conn = duckdb.connect(str(db_path), read_only=True)
        gold_rows = conn.execute(case.gold_sql).fetchall()
        agent_rows = conn.execute(result.sql_queries[-1]).fetchall()
        conn.close()
    """
    return execution_accuracy_details(case, result, db_path)["passed"]


def execution_accuracy_details(case, result, db_path: str | Path) -> dict:
    """
    Return execution accuracy plus enough context to explain the result.
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
    Use an LLM to grade the agent's final answer against the gold answer.

    Returns a dict: {"verdict": "correct"|"partial"|"incorrect", "reason": "..."}

    Implementation notes:
    -------------------------
    1. Build a grading prompt that includes:
       - The original question (case.question)
       - The reference answer (case.gold_answer)
       - The agent's final answer (result.final_answer)
       Instruct the model to return STRICT JSON ONLY with no prose outside the
       JSON block:
           {"verdict": "correct"|"partial"|"incorrect", "reason": "<one sentence>"}

    2. Call the Anthropic Messages API using claude-haiku-4-5 (fast + cheap).
       Use the official `anthropic` SDK — already in requirements.txt.

    3. Parse the response robustly:
       - Strip any markdown code fences (```json ... ```) from the response text.
       - Parse the stripped text with json.loads().
       - If parsing fails, return {"verdict": "error", "reason": "<raw text>"}.

    4. Return the parsed dict.

    Suggested implementation skeleton:
        import anthropic, json, re

        client = anthropic.Anthropic()
        prompt = f\"\"\"...\"\"\"
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # strip code fences
        raw = re.sub(r"^```(?:json)?\\n?", "", raw)
        raw = re.sub(r"\\n?```$", "", raw)
        return json.loads(raw)

    Note: the judge is non-deterministic. Run multiple times and average if you
    want stable signal. Treat it as a soft, complementary signal to
    execution_accuracy.
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
