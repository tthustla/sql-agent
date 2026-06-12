"""
Tool implementations for the SQL agent.

Exposes:
  get_schema()         -> str
  run_sql(query)       -> str
  profile_table(table) -> str
  TOOLS                list of Anthropic tool-schema dicts
  TOOL_MAP             dict mapping tool name -> callable
"""

from pathlib import Path

import duckdb

DB_PATH = Path(__file__).parent.parent / "warehouse.duckdb"
ROW_CAP = 50


def _connect() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Run data/build_db.py first."
        )
    return duckdb.connect(str(DB_PATH), read_only=True)


def get_schema() -> str:
    """Return all tables, columns, and types as readable text."""
    con = _connect()
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()

    lines = []
    for (table_name,) in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name=? ORDER BY ordinal_position",
            [table_name],
        ).fetchall()
        lines.append(f"Table: {table_name}")
        for col_name, data_type in cols:
            lines.append(f"  {col_name}  {data_type}")
        lines.append("")

    con.close()
    return "\n".join(lines).strip()


def run_sql(query: str) -> str:
    """Execute a SELECT/WITH query and return results as text (capped at 50 rows)."""
    normalized = query.strip().upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return "ERROR: Only SELECT or WITH queries are allowed."

    try:
        con = _connect()
        rel = con.execute(query)
        col_names = [desc[0] for desc in rel.description]
        rows = rel.fetchmany(ROW_CAP + 1)
        con.close()
    except Exception as exc:
        return f"ERROR: {exc}"

    truncated = len(rows) > ROW_CAP
    rows = rows[:ROW_CAP]

    if not rows:
        return "(no rows returned)"

    # Format as aligned columns
    col_widths = [len(c) for c in col_names]
    str_rows = []
    for row in rows:
        str_row = [str(v) if v is not None else "NULL" for v in row]
        str_rows.append(str_row)
        for i, cell in enumerate(str_row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "  ".join("-" * w for w in col_widths)
    header = "  ".join(c.ljust(col_widths[i]) for i, c in enumerate(col_names))

    lines = [header, sep]
    for str_row in str_rows:
        lines.append("  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(str_row)))

    if truncated:
        lines.append(f"... (output capped at {ROW_CAP} rows)")

    return "\n".join(lines)


def profile_table(table: str) -> str:
    """Return row count, per-column null counts, and sample values for a table."""
    con = _connect()

    # Validate table name to prevent injection
    valid_tables = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    }
    if table not in valid_tables:
        con.close()
        return f"ERROR: Table '{table}' not found. Valid tables: {', '.join(sorted(valid_tables))}"

    row_count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    cols = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='main' AND table_name=? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    col_names = [c[0] for c in cols]

    lines = [f"Table: {table}", f"Row count: {row_count}", ""]

    for col in col_names:
        null_count = con.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NULL'
        ).fetchone()[0]
        samples = con.execute(
            f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 5'
        ).fetchall()
        sample_vals = ", ".join(str(r[0]) for r in samples)
        lines.append(f"  {col}")
        lines.append(f"    nulls  : {null_count}")
        lines.append(f"    samples: {sample_vals}")

    con.close()
    return "\n".join(lines)


# ── Anthropic tool schemas ─────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_schema",
        "description": (
            "Return the schema of the warehouse: all tables with their column names and data types. "
            "Call this first when you need to understand what data is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Execute a SQL SELECT or WITH query against the warehouse and return the results as text. "
            "Output is capped at 50 rows. Only read-only queries (SELECT / WITH) are permitted."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A valid DuckDB SQL SELECT or WITH query.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "profile_table",
        "description": (
            "Return a profile of a single table: total row count, per-column null counts, "
            "and a few sample distinct values. Useful for data exploration before writing queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "The name of the table to profile (e.g. 'orders').",
                }
            },
            "required": ["table"],
        },
    },
]

TOOL_MAP = {
    "get_schema": get_schema,
    "run_sql": run_sql,
    "profile_table": profile_table,
}
