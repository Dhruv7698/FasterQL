# ⚡ FasterQL — Dynamic SQL & Database Query Performance Bottleneck Auditor

A lightweight, 100% offline static SQL AST analyzer built with **Python**, **`sqlparse`**, and **Streamlit**.

## Quick Start (Local Setup in 60 Seconds)

```bash
# 1. Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# 2. Install lightweight dependencies
pip install -r requirements.txt

# 3. Launch the live Streamlit dashboard
streamlit run app.py
```

## What the Prototype Does
1. **Ingests Raw SQL**: Paste any raw SQL query or upload a `.sql` file (`sample_queries.sql` is included for instant testing).
2. **AST Tokenization & Structural Breakdown**: Uses `sqlparse` to break the query into structural clauses (`SELECT` projections, `FROM`/`JOIN` tables, `WHERE` predicates, nested subqueries, and `ORDER BY`/`LIMIT`).
3. **Flags Anti-Patterns with Database Planner Reasoning**:
   - `FQL-001`: `SELECT *` unbounded projection (prevents covering index-only scans).
   - `FQL-002`: Leading wildcard `LIKE '%term%'` (non-sargable predicate; forces `O(N)` full table scan).
   - `FQL-003`: Function wrapping an indexed column in `WHERE` (`YEAR(created_at) = 2026`, `LOWER(email)`).
   - `FQL-004`: Nested `IN (SELECT ...)` subquery (triggers nested-loop evaluation; rewrites to `EXISTS` / `JOIN`).
   - `FQL-005`: Implicit comma join (`FROM a, b WHERE ...`) risking accidental Cartesian product.
   - `FQL-006`: Unindexed filter/sort predicates (`CREATE INDEX CONCURRENTLY` recommendation).
   - `FQL-007`: Unbounded `ORDER BY` without `LIMIT` (triggers external disk merge sort instead of Top-N heap sort).
4. **Calculates Query Complexity Score**: Computes Before vs. After scores across 4 cost dimensions (`I/O & Scan`, `Index & SARGability`, `Join & Subquery`, `Memory & Sort`) and plots a side-by-side comparison bar chart.
5. **Auto-Rewrites SQL + Generates Index DDL**: Outputs a production-ready SQL rewrite and copyable `CREATE INDEX CONCURRENTLY` statements.
