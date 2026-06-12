"""
Tests for src/tools.py.

All tests use the `test_db` fixture (conftest.py) which patches tools.DB_PATH
to a temporary database — the real warehouse.duckdb is never touched.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import tools


# ── get_schema ─────────────────────────────────────────────────────────────────

def test_get_schema_lists_all_tables(test_db):
    schema = tools.get_schema()
    assert "customers" in schema
    assert "products" in schema
    assert "orders" in schema


def test_get_schema_lists_columns(test_db):
    schema = tools.get_schema()
    assert "signup_date" in schema
    assert "category" in schema
    assert "order_date" in schema


def test_get_schema_lists_types(test_db):
    schema = tools.get_schema()
    assert "VARCHAR" in schema
    assert "INTEGER" in schema


def test_get_schema_missing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DB_PATH", tmp_path / "nonexistent.duckdb")
    with pytest.raises(FileNotFoundError):
        tools.get_schema()


# ── run_sql ────────────────────────────────────────────────────────────────────

def test_run_sql_basic_select(test_db):
    result = tools.run_sql("SELECT id, name FROM customers ORDER BY id")
    assert "Alice Smith" in result
    assert "Bob Jones" in result


def test_run_sql_with_cte(test_db):
    result = tools.run_sql(
        "WITH c AS (SELECT COUNT(*) AS n FROM orders) SELECT n FROM c"
    )
    assert "5" in result


def test_run_sql_empty_result(test_db):
    result = tools.run_sql("SELECT * FROM customers WHERE id = 999")
    assert result == "(no rows returned)"


def test_run_sql_rejects_insert(test_db):
    result = tools.run_sql("INSERT INTO customers VALUES (99, 'X', 'US', '2024-01-01')")
    assert result.startswith("ERROR")


def test_run_sql_rejects_drop(test_db):
    result = tools.run_sql("DROP TABLE customers")
    assert result.startswith("ERROR")


def test_run_sql_rejects_update(test_db):
    result = tools.run_sql("UPDATE customers SET name='X' WHERE id=1")
    assert result.startswith("ERROR")


def test_run_sql_syntax_error_returns_error_string(test_db):
    result = tools.run_sql("SELECT FROM WHERE")
    assert result.startswith("ERROR")


def test_run_sql_row_cap(test_db, monkeypatch):
    monkeypatch.setattr(tools, "ROW_CAP", 2)
    result = tools.run_sql("SELECT * FROM orders ORDER BY id")
    assert "capped at 2 rows" in result


def test_run_sql_join(test_db):
    result = tools.run_sql("""
        SELECT c.name, p.name AS product
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN products  p ON o.product_id  = p.id
        ORDER BY o.id
        LIMIT 1
    """)
    assert "Alice Smith" in result
    assert "Wireless Headphones" in result


# ── profile_table ──────────────────────────────────────────────────────────────

def test_profile_table_row_count(test_db):
    result = tools.profile_table("orders")
    assert "Row count: 5" in result


def test_profile_table_shows_columns(test_db):
    result = tools.profile_table("customers")
    assert "name" in result
    assert "country" in result
    assert "signup_date" in result


def test_profile_table_null_counts(test_db):
    result = tools.profile_table("customers")
    assert "nulls  : 0" in result


def test_profile_table_sample_values(test_db):
    result = tools.profile_table("customers")
    assert "US" in result or "CA" in result or "GB" in result


def test_profile_table_invalid_name(test_db):
    result = tools.profile_table("nonexistent_table")
    assert result.startswith("ERROR")
    assert "nonexistent_table" in result


# ── TOOLS schema and TOOL_MAP ──────────────────────────────────────────────────

def test_tools_list_has_three_entries():
    assert len(tools.TOOLS) == 3


def test_tools_list_names():
    names = {t["name"] for t in tools.TOOLS}
    assert names == {"get_schema", "run_sql", "profile_table"}


def test_tools_have_required_keys():
    for tool in tools.TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool


def test_tool_map_keys():
    assert set(tools.TOOL_MAP.keys()) == {"get_schema", "run_sql", "profile_table"}


def test_tool_map_values_are_callable():
    for fn in tools.TOOL_MAP.values():
        assert callable(fn)
