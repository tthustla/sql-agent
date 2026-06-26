"""
Eval cases for the text-to-SQL agent.

Each EvalCase pairs a natural-language question with the ground truth needed to
score the agent's response. There are two scoring signals:
  - execution_accuracy: run gold_sql and the agent's last SQL, compare result sets
  - llm_judge: compare gold_answer and the agent's final_answer via an LLM grader

The suite contains 20 cases covering lookups, aggregations, multi-hop joins,
date ranges, NULL handling, HAVING clauses, ambiguous phrasing, and questions
that cannot be answered from the schema.
"""

from dataclasses import dataclass


@dataclass
class EvalCase:
    id: str
    question: str
    gold_sql: str | None  # None for unanswerable cases
    gold_answer: str
    category: str
    ordered: bool  # True if row order is part of correctness


CASES: list[EvalCase] = [
    EvalCase(
        id="lookup-001",
        question="What is the price of the Mechanical Keyboard?",
        gold_sql="SELECT price FROM products WHERE name = 'Mechanical Keyboard'",
        gold_answer="129.99",
        category="lookup",
        ordered=False,
    ),
    EvalCase(
        id="lookup-002",
        question="What are the category and price of the Mechanical Keyboard?",
        gold_sql=(
            "SELECT category, price "
            "FROM products WHERE name = 'Mechanical Keyboard'"
        ),
        gold_answer="Electronics, 129.99",
        category="lookup",
        ordered=False,
    ),
    EvalCase(
        id="lookup-003",
        question="Which country is Uma Garcia from, and when did they sign up?",
        gold_sql=(
            "SELECT country, signup_date "
            "FROM customers WHERE name = 'Uma Garcia'"
        ),
        gold_answer="Uma Garcia is from the US and signed up on 2024-10-08.",
        category="lookup",
        ordered=False,
    ),
    EvalCase(
        id="agg-001",
        question="How many total orders are in the database?",
        gold_sql="SELECT COUNT(*) FROM orders",
        gold_answer="500",
        category="aggregation",
        ordered=False,
    ),
    EvalCase(
        id="agg-002",
        question="How many distinct countries are represented in the customer base?",
        gold_sql="SELECT COUNT(DISTINCT country) FROM customers",
        gold_answer="8",
        category="aggregation",
        ordered=False,
    ),
    EvalCase(
        id="agg-003",
        question="What is the average product price?",
        gold_sql="SELECT AVG(price) FROM products",
        gold_answer="37.9415, or about $37.94 rounded to two decimal places",
        category="aggregation",
        ordered=False,
    ),
    EvalCase(
        id="agg-004",
        question="How many items have been ordered in total?",
        gold_sql="SELECT SUM(quantity) FROM orders",
        gold_answer="985 items have been ordered in total.",
        category="aggregation",
        ordered=False,
    ),
    EvalCase(
        id="date-001",
        question="How many orders were placed in January 2025?",
        gold_sql=(
            "SELECT COUNT(*) FROM orders "
            "WHERE order_date >= DATE '2025-01-01' "
            "AND order_date < DATE '2025-02-01'"
        ),
        gold_answer="39 orders were placed in January 2025.",
        category="date_range",
        ordered=False,
    ),
    EvalCase(
        id="date-002",
        question=(
            "How many orders were placed in each month of the first quarter "
            "of 2025? List the months chronologically."
        ),
        gold_sql=(
            "SELECT strftime(order_date, '%Y-%m') AS month, COUNT(*) AS orders "
            "FROM orders "
            "WHERE order_date >= DATE '2025-01-01' "
            "AND order_date < DATE '2025-04-01' "
            "GROUP BY month ORDER BY month"
        ),
        gold_answer="2025-01: 39; 2025-02: 59; 2025-03: 62.",
        category="date_range",
        ordered=True,
    ),
    EvalCase(
        id="date-003",
        question=(
            "How many customers signed up from January 1 through "
            "March 31, 2025, inclusive?"
        ),
        gold_sql=(
            "SELECT COUNT(*) FROM customers "
            "WHERE signup_date BETWEEN DATE '2025-01-01' AND DATE '2025-03-31'"
        ),
        gold_answer="15 customers signed up during that date range.",
        category="date_range",
        ordered=False,
    ),
    EvalCase(
        id="null-001",
        question="How many orders have a missing quantity?",
        gold_sql="SELECT COUNT(*) FROM orders WHERE quantity IS NULL",
        gold_answer="No orders have a missing quantity.",
        category="null_handling",
        ordered=False,
    ),
    EvalCase(
        id="null-002",
        question="How many customers have never placed an order?",
        gold_sql=(
            "SELECT COUNT(*) FROM customers c "
            "LEFT JOIN orders o ON o.customer_id = c.id "
            "WHERE o.id IS NULL"
        ),
        gold_answer="1 customer has never placed an order.",
        category="null_handling",
        ordered=False,
    ),
    EvalCase(
        id="join-001",
        question="What are the top 5 most-ordered products and how many times was each ordered? If there are ties, break them alphabetically by product name.",
        gold_sql=(
            "SELECT p.name, COUNT(*) AS order_count "
            "FROM orders o JOIN products p ON o.product_id = p.id "
            "GROUP BY p.name ORDER BY order_count DESC, p.name ASC LIMIT 5"
        ),
        gold_answer=(
            "1. Insulated Tumbler — 34 orders\n"
            "2. Standing Desk Mat — 32 orders\n"
            "3. Mechanical Keyboard — 31 orders\n"
            "4. Yoga Mat — 30 orders\n"
            "5. Jump Rope — 29 orders"
        ),
        category="join",
        ordered=True,
    ),
    EvalCase(
        id="join-002",
        question=(
            "Which three countries ordered the most units of Electronics "
            "products? Break ties alphabetically by country."
        ),
        gold_sql=(
            "SELECT c.country, SUM(o.quantity) AS units "
            "FROM customers c "
            "JOIN orders o ON o.customer_id = c.id "
            "JOIN products p ON p.id = o.product_id "
            "WHERE p.category = 'Electronics' "
            "GROUP BY c.country "
            "ORDER BY units DESC, c.country ASC LIMIT 3"
        ),
        gold_answer="1. US: 71 units; 2. BR: 30 units; 3. JP: 26 units.",
        category="join",
        ordered=True,
    ),
    EvalCase(
        id="join-003",
        question="How many customers in Canada have ordered an Electronics product?",
        gold_sql=(
            "SELECT COUNT(DISTINCT c.id) "
            "FROM customers c "
            "JOIN orders o ON o.customer_id = c.id "
            "JOIN products p ON p.id = o.product_id "
            "WHERE c.country = 'CA' AND p.category = 'Electronics'"
        ),
        gold_answer="4 Canadian customers have ordered an Electronics product.",
        category="join",
        ordered=False,
    ),
    EvalCase(
        id="join-004",
        question=(
            "Which customer bought the most items in total, and how many? "
            "Break ties alphabetically by customer name."
        ),
        gold_sql=(
            "SELECT c.name, SUM(o.quantity) AS units "
            "FROM customers c JOIN orders o ON o.customer_id = c.id "
            "GROUP BY c.id, c.name "
            "ORDER BY units DESC, c.name ASC LIMIT 1"
        ),
        gold_answer="Zoe Smith bought the most items, with 31 units.",
        category="join",
        ordered=True,
    ),
    EvalCase(
        id="having-001",
        question=(
            "Which countries have at least 10 customers? Sort by customer "
            "count descending, then country alphabetically."
        ),
        gold_sql=(
            "SELECT country, COUNT(*) AS customers "
            "FROM customers GROUP BY country "
            "HAVING COUNT(*) >= 10 "
            "ORDER BY customers DESC, country ASC"
        ),
        gold_answer="US: 38; BR: 12; CA: 12; JP: 12; FR: 11.",
        category="having",
        ordered=True,
    ),
    EvalCase(
        id="having-002",
        question=(
            "Which product categories have an average price above $40? "
            "Round to two decimal places and list highest average first."
        ),
        gold_sql=(
            "SELECT category, ROUND(AVG(price), 2) AS average_price "
            "FROM products GROUP BY category "
            "HAVING AVG(price) > 40 "
            "ORDER BY average_price DESC, category ASC"
        ),
        gold_answer="Electronics: $76.24; Bags: $42.24.",
        category="having",
        ordered=True,
    ),
    EvalCase(
        id="unanswerable-001",
        question="What is the average customer satisfaction rating for each product?",
        gold_sql=None,
        gold_answer=(
            "This cannot be answered because the schema has no customer "
            "satisfaction rating column."
        ),
        category="unanswerable",
        ordered=False,
    ),
    EvalCase(
        id="unanswerable-002",
        question="How much revenue was refunded in 2025?",
        gold_sql=None,
        gold_answer=(
            "This cannot be answered because the schema contains no refund "
            "or return data."
        ),
        category="unanswerable",
        ordered=False,
    ),
]
