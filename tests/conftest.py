"""
Shared fixtures for all tests.
"""

import os
from datetime import date

import duckdb
import pytest

# Ensure agent.py can be imported without a real API key
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """
    Creates a minimal in-memory-style DuckDB warehouse with the same schema
    as the real warehouse, then patches tools.DB_PATH to point at it.
    All tool tests should use this fixture instead of the real warehouse.
    """
    import tools

    db_file = tmp_path / "test_warehouse.duckdb"
    con = duckdb.connect(str(db_file))

    con.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            country VARCHAR,
            signup_date DATE
        )
    """)
    con.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            category VARCHAR,
            price DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            order_date DATE
        )
    """)

    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", [
        (1, "Alice Smith",  "US", date(2024, 1, 15)),
        (2, "Bob Jones",    "CA", date(2024, 3, 20)),
        (3, "Carol Lee",    "GB", date(2024, 6, 10)),
    ])
    con.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", [
        (1, "Wireless Headphones", "Electronics", 79.99),
        (2, "Yoga Mat",            "Fitness",     39.99),
        (3, "Coffee Mug",          "Kitchen",     16.99),
    ])
    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", [
        (1, 1, 1, 2, date(2024, 8,  1)),
        (2, 2, 2, 1, date(2024, 9, 15)),
        (3, 3, 3, 3, date(2024, 10, 5)),
        (4, 1, 2, 1, date(2025, 1, 20)),
        (5, 2, 1, 1, date(2025, 3, 10)),
    ])

    con.close()
    monkeypatch.setattr(tools, "DB_PATH", db_file)
    return db_file
