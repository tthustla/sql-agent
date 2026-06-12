"""
Generates a synthetic e-commerce warehouse in warehouse.duckdb.
Run from the project root: python data/build_db.py
"""

import random
import string
from datetime import date, timedelta
from pathlib import Path

import duckdb

SEED = 42
random.seed(SEED)

DB_PATH = Path(__file__).parent.parent / "warehouse.duckdb"

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Elena", "Frank", "Grace", "Hiro",
    "Iris", "James", "Kira", "Liam", "Maya", "Noah", "Olivia", "Pedro",
    "Quinn", "Rosa", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander",
    "Yara", "Zoe",
]
LAST_NAMES = [
    "Smith", "Jones", "Lee", "Garcia", "Patel", "Kim", "Chen", "Brown",
    "Wilson", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris",
    "Martin", "Thompson", "Martinez", "Robinson", "Clark",
]
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "FR", "AU", "JP", "BR"]

PRODUCT_CATALOG = [
    ("Wireless Headphones", "Electronics", 79.99),
    ("USB-C Hub", "Electronics", 34.99),
    ("Mechanical Keyboard", "Electronics", 129.99),
    ("Webcam HD", "Electronics", 59.99),
    ("Standing Desk Mat", "Office", 45.00),
    ("Notebook Set", "Office", 12.99),
    ("Desk Lamp", "Office", 28.50),
    ("Cable Organizer", "Office", 9.99),
    ("Yoga Mat", "Fitness", 39.99),
    ("Resistance Bands", "Fitness", 19.99),
    ("Water Bottle", "Fitness", 24.99),
    ("Jump Rope", "Fitness", 14.99),
    ("Coffee Mug", "Kitchen", 16.99),
    ("French Press", "Kitchen", 29.99),
    ("Insulated Tumbler", "Kitchen", 22.99),
    ("Espresso Cups Set", "Kitchen", 18.50),
    ("Backpack", "Bags", 89.99),
    ("Tote Bag", "Bags", 34.99),
    ("Laptop Sleeve", "Bags", 27.99),
    ("Passport Holder", "Bags", 15.99),
]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(str(DB_PATH))

    # ── customers ──────────────────────────────────────────────────────────────
    con.execute("""
        CREATE TABLE customers (
            id          INTEGER PRIMARY KEY,
            name        VARCHAR,
            country     VARCHAR,
            signup_date DATE
        )
    """)

    signup_start = date(2024, 1, 1)
    signup_end   = date(2025, 6, 1)
    customers = []
    for i in range(1, 101):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        country = random.choice(COUNTRIES)
        signup = random_date(signup_start, signup_end)
        customers.append((i, name, country, signup))

    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)

    # ── products ───────────────────────────────────────────────────────────────
    con.execute("""
        CREATE TABLE products (
            id       INTEGER PRIMARY KEY,
            name     VARCHAR,
            category VARCHAR,
            price    DOUBLE
        )
    """)

    products = [(i + 1, name, cat, price) for i, (name, cat, price) in enumerate(PRODUCT_CATALOG)]
    con.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)

    # ── orders ─────────────────────────────────────────────────────────────────
    # Weight recent months higher so trends are visible
    con.execute("""
        CREATE TABLE orders (
            id          INTEGER PRIMARY KEY,
            customer_id INTEGER,
            product_id  INTEGER,
            quantity    INTEGER,
            order_date  DATE
        )
    """)

    order_start = date(2024, 7, 1)
    order_end   = date(2025, 6, 30)
    total_days  = (order_end - order_start).days

    orders = []
    for i in range(1, 501):
        cust_id = random.randint(1, 100)
        prod_id = random.randint(1, len(PRODUCT_CATALOG))
        qty     = random.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0]
        # Skew toward more recent dates so monthly trends show growth
        day_offset = int(random.betavariate(2, 1) * total_days)
        odate = order_start + timedelta(days=day_offset)
        orders.append((i, cust_id, prod_id, qty, odate))

    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    con.close()

    print(f"warehouse.duckdb created at {DB_PATH}")
    print(f"  customers : {len(customers):>5} rows")
    print(f"  products  : {len(products):>5} rows")
    print(f"  orders    : {len(orders):>5} rows")


if __name__ == "__main__":
    build()
