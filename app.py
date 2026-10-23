"""
FasterQL — Dynamic SQL & Database Query Performance Bottleneck Auditor
Live Streamlit Prototype
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from auditor import audit_sql_query, HAS_SQLPARSE

st.set_page_config(
    page_title="FasterQL | SQL Performance Bottleneck Auditor",
    page_icon="⚡",
    layout="wide",
)

PRESET_QUERIES = {
    "1. E-Commerce Order Timeout (SELECT *, LIKE '%...', Subquery, Non-Sargable Date)": """SELECT *
FROM orders
WHERE customer_email LIKE '%@enterprise.io'
  AND YEAR(created_at) = 2026
  AND user_id IN (
      SELECT id FROM users WHERE status = 'active'
  )
ORDER BY created_at DESC;""",
    "2. Legacy Implicit Join & Unbounded Scan": """SELECT *
FROM users u, orders o, payments p
WHERE u.id = o.user_id
  AND o.id = p.order_id
  AND LOWER(u.email) = 'admin@company.org'
ORDER BY o.created_at DESC;""",
    "3. Clean Production Query (Already Optimized)": """SELECT id, user_id, total_amount, created_at
FROM orders
WHERE user_id = 48291
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;""",
}

st.title("⚡ FasterQL — Dynamic SQL & Database Query Performance Bottleneck Auditor")
st.caption(
    "Zero-dependency AST static analyzer that detects non-sargable predicates, full-table scans, "
    "and nested-loop traps before your query hits production."
)

with st.sidebar:
    st.header("1. Load or Upload SQL")
    preset_choice = st.selectbox("Choose a Demo Scenario:", list(PRESET_QUERIES.keys()))
    uploaded_file = st.file_uploader("Or upload a raw .sql file", type=["sql", "txt"])
    table_scale = st.select_slider(
        "Simulated Table Cardinality (Rows)",
        options=["100K", "1M", "10M", "50M"],
        value="1M",
    )
    st.markdown("---")
    st.markdown(
        f"**Parser Engine:** `{'sqlparse AST' if HAS_SQLPARSE else 'Regex AST Fallback'}`\n\n"
        "**Network Calls:** `0 (100% Offline Deterministic)`"
    )

default_sql = PRESET_QUERIES[preset_choice]
if uploaded_file is not None:
    default_sql = uploaded_file.read().decode("utf-8", errors="ignore")

sql_input = st.text_area("Paste Raw SQL Query to Audit:", value=default_sql, height=180)

if st.button("🔍 Audit & Optimize Query", type="primary", use_container_width=True) or sql_input:
    result = audit_sql_query(sql_input)
    reduction_pct = round(
        ((result.original_score - result.optimized_score) / max(1, result.original_score)) * 100
    )

    # Top KPI Metrics Row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Original Complexity Score",
        f"{result.original_score} / 100",
        delta=result.complexity_class_before,
        delta_color="inverse",
    )
    col2.metric(
        "Optimized Complexity Score",
        f"{result.optimized_score} / 100",
        delta=f"-{reduction_pct}% Complexity Reduction",
        delta_color="normal",
    )
    col3.metric("Bottlenecks Flagged", str(len(result.issues)), delta="AST Pattern Rules")
    col4.metric("Optimized Time Complexity", result.complexity_class_after.split()[0], delta="B-Tree Index Seek")

    st.markdown("---")

    # Side-by-Side Query Rewrite & Chart
    left_col, right_col = st.columns([1.15, 1])

    with left_col:
        st.subheader("🛠️ Auto-Rewritten Production SQL & Index DDL")
        st.code(result.optimized_sql, language="sql")
        st.markdown("**Recommended Index DDL (Zero-Lock Creation):**")
        st.code("\n".join(result.index_ddl), language="sql")

    with right_col:
        st.subheader("📊 Side-by-Side Complexity Reduction Breakdown")
        chart_df = pd.DataFrame(
            {
                "Category": list(result.category_scores_before.keys()),
                "Before (Raw SQL)": list(result.category_scores_before.values()),
                "After (FasterQL Optimized)": list(result.category_scores_after.values()),
            }
        ).set_index("Category")
        st.bar_chart(chart_df)

    st.markdown("---")

    # Detailed Bottleneck Cards
    st.subheader("🚨 Detected Bottlenecks & Database Planner Diagnostics")
    if not result.issues:
        st.success("No major anti-patterns detected! This query is already structured for B-Tree index seeks.")
    else:
        for issue in result.issues:
            badge = "🔴" if issue.severity == "CRITICAL" else ("🟠" if issue.severity == "HIGH" else "🟡")
            with st.expander(
                f"{badge} [{issue.rule_id}] {issue.title} — Severity: {issue.severity} (+{issue.penalty} Penalty)",
                expanded=True,
            ):
                st.markdown(f"**Offending AST Pattern:** `{issue.offending_snippet}`")
                st.markdown(f"**Why It Stalls Production:** {issue.explanation}")
                st.markdown(f"**How FasterQL Fixes It:** {issue.recommendation}")

    # Structural AST Breakdown
    with st.expander("🧬 View Structural AST & Token Breakdown (sqlparse)"):
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            st.json(
                {
                    "Tables Referenced": result.structural_breakdown["tables"],
                    "Detected Aliases": result.structural_breakdown["aliases"],
                    "WHERE Filter Columns": result.structural_breakdown["where_columns"],
                    "ORDER BY Columns": result.structural_breakdown["order_columns"],
                    "Subqueries Count": result.structural_breakdown["subquery_count"],
                    "Has Pagination LIMIT": result.structural_breakdown["has_limit"],
                }
            )
        with b_col2:
            st.dataframe(pd.DataFrame(result.structural_breakdown["tokens"]), use_container_width=True, height=240)
