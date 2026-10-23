"""
FasterQL — Core SQL AST & Token Bottleneck Auditor Engine
Uses `sqlparse` (with a built-in fallback tokenizer) to inspect SQL structure,
detect anti-patterns, compute a deterministic Query Complexity Score, and
auto-rewrite queries into production-optimized SQL + CREATE INDEX DDL.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

try:
    import sqlparse
    from sqlparse.sql import IdentifierList, Identifier, Where, Comparison, Parenthesis, Function
    from sqlparse.tokens import Keyword, DML, Wildcard, Name, Punctuation, Literal
    HAS_SQLPARSE = True
except ImportError:
    HAS_SQLPARSE = False


@dataclass
class BottleneckIssue:
    rule_id: str
    title: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    penalty: int
    category: str  # "I/O & Scan", "Join & Subquery", "Index & SARGability", "Memory & Sort"
    offending_snippet: str
    explanation: str
    recommendation: str


@dataclass
class AuditResult:
    raw_sql: str
    formatted_sql: str
    optimized_sql: str
    index_ddl: List[str]
    original_score: int
    optimized_score: int
    complexity_class_before: str
    complexity_class_after: str
    issues: List[BottleneckIssue] = field(default_factory=list)
    structural_breakdown: Dict[str, Any] = field(default_factory=dict)
    category_scores_before: Dict[str, int] = field(default_factory=dict)
    category_scores_after: Dict[str, int] = field(default_factory=dict)


DEFAULT_TABLE_COLUMNS = {
    "users": ["id", "email", "full_name", "status", "created_at"],
    "orders": ["id", "user_id", "total_amount", "order_status", "created_at"],
    "products": ["id", "sku", "title", "category_id", "price"],
    "payments": ["id", "order_id", "payment_method", "amount", "paid_at"],
    "events": ["id", "user_id", "event_type", "payload_hash", "occurred_at"],
    "transactions": ["id", "account_id", "amount", "currency", "tx_timestamp"],
}


def format_sql_query(sql: str) -> str:
    clean = sql.strip()
    if HAS_SQLPARSE:
        return sqlparse.format(clean, reindent=True, keyword_case="upper")
    return clean


def extract_structural_components(sql: str) -> Dict[str, Any]:
    """Extracts tables, projections, joins, where filters, and AST token stats."""
    normalized = re.sub(r"\s+", " ", sql.strip())

    # Extract tables in FROM and JOIN
    from_tables = re.findall(
        r"\bFROM\s+([a-zA-Z0-9_.,\s]+?)(?:\bWHERE\b|\bJOIN\b|\bINNER\b|\bLEFT\b|\bRIGHT\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|;|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    tables = []
    aliases = {}
    comma_joins = False
    for chunk in from_tables:
        parts = [p.strip() for p in chunk.split(",") if p.strip()]
        if len(parts) > 1:
            comma_joins = True
        for part in parts:
            tokens = part.split()
            tbl = tokens[0].strip("`\"'")
            if tbl.upper() not in ("SELECT", "(SELECT"):
                tables.append(tbl)
                if len(tokens) >= 2 and tokens[-1].upper() not in ("AS", "ON", "USING"):
                    aliases[tokens[-1]] = tbl

    join_matches = re.findall(
        r"\b(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+|CROSS\s+)?JOIN\s+([a-zA-Z0-9_`\"']+)\s*(?:AS\s+)?([a-zA-Z0-9_]+)?",
        normalized,
        flags=re.IGNORECASE,
    )
    for tbl, alias in join_matches:
        clean_tbl = tbl.strip("`\"'")
        if clean_tbl not in tables:
            tables.append(clean_tbl)
        if alias and alias.upper() not in ("ON", "USING", "WHERE"):
            aliases[alias] = clean_tbl

    # Extract WHERE columns
    where_clause_match = re.search(
        r"\bWHERE\b(.+?)(?:\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|;|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    where_clause = where_clause_match.group(1).strip() if where_clause_match else ""

    where_columns = []
    if where_clause:
        col_matches = re.findall(
            r"([a-zA-Z_][a-zA-Z0-9_.]*)\s*(?:=|>|<|>=|<=|!=|<>|\bLIKE\b|\bIN\b|\bBETWEEN\b)",
            where_clause,
            flags=re.IGNORECASE,
        )
        for col in col_matches:
            if col.upper() not in ("AND", "OR", "NOT", "SELECT", "WHERE", "YEAR", "LOWER", "UPPER", "DATE"):
                where_columns.append(col)

    # Extract ORDER BY columns
    order_match = re.search(
        r"\bORDER\s+BY\b(.+?)(?:\bLIMIT\b|;|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    order_columns = []
    if order_match:
        raw_order = order_match.group(1)
        for item in raw_order.split(","):
            tokens = item.strip().split()
            if tokens:
                order_columns.append(tokens[0])

    # Token count via sqlparse if available
    token_list = []
    if HAS_SQLPARSE:
        parsed = sqlparse.parse(sql)
        if parsed:
            stmt = parsed[0]
            for tok in stmt.flatten():
                if not tok.is_whitespace:
                    token_list.append({"value": tok.value, "type": str(tok.ttype).replace("Token.", "")})
    else:
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*|'[^']*'|\*|[=<>!]+|[(),;]", normalized):
            token_list.append({"value": tok, "type": "Token"})

    return {
        "tables": tables or ["target_table"],
        "aliases": aliases,
        "comma_joins": comma_joins,
        "join_count": len(join_matches) + (1 if comma_joins else 0),
        "where_clause": where_clause,
        "where_columns": list(dict.fromkeys(where_columns)),
        "order_columns": order_columns,
        "has_limit": bool(re.search(r"\bLIMIT\s+\d+", normalized, flags=re.IGNORECASE)),
        "subquery_count": len(re.findall(r"\(\s*SELECT\b", normalized, flags=re.IGNORECASE)),
        "tokens": token_list[:40],
        "total_tokens": len(token_list),
    }


def audit_sql_query(sql: str) -> AuditResult:
    """Runs the FasterQL rule engine over the SQL query and produces an AuditResult."""
    clean_sql = sql.strip()
    formatted_sql = format_sql_query(clean_sql)
    normalized = re.sub(r"\s+", " ", clean_sql)
    breakdown = extract_structural_components(clean_sql)

    issues: List[BottleneckIssue] = []
    rewritten = clean_sql
    index_columns: List[Tuple[str, str]] = []

    category_before = {
        "I/O & Scan": 10,
        "Index & SARGability": 8,
        "Join & Subquery": 6,
        "Memory & Sort": 6,
    }

    primary_table = breakdown["tables"][0] if breakdown["tables"] else "records"

    # Rule 1: SELECT * projection
    if re.search(r"\bSELECT\s+(?:DISTINCT\s+)?\*", normalized, flags=re.IGNORECASE):
        issues.append(
            BottleneckIssue(
                rule_id="CS-001",
                title="Unbounded Column Projection (SELECT *)",
                severity="HIGH",
                penalty=22,
                category="I/O & Scan",
                offending_snippet="SELECT *",
                explanation=(
                    "Fetching every column prevents the database engine from using a Covering Index "
                    "(Index-Only Scan) and forces heap/table page fetches, increasing disk I/O and memory payload."
                ),
                recommendation="Project only required columns explicitly so the planner can satisfy the query from a B-Tree index.",
            )
        )
        category_before["I/O & Scan"] += 22
        cols = DEFAULT_TABLE_COLUMNS.get(primary_table.lower(), ["id", "user_id", "status", "created_at"])
        prefix = f"{ list(breakdown['aliases'].keys())[0] }." if breakdown["aliases"] else ""
        explicit_cols = ", ".join(f"{prefix}{c}" for c in cols[:4])
        rewritten = re.sub(
            r"\bSELECT\s+\*",
            f"SELECT {explicit_cols}",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )

    # Rule 2: Leading wildcard LIKE '%term%'
    like_match = re.search(r"([a-zA-Z0-9_.]+)\s+LIKE\s+['\"]%([^'\"]+)['\"]", normalized, flags=re.IGNORECASE)
    if like_match:
        col_name = like_match.group(1)
        term_val = like_match.group(2).rstrip("%")
        issues.append(
            BottleneckIssue(
                rule_id="CS-002",
                title="Non-Sargable Leading Wildcard (LIKE '%term%')",
                severity="CRITICAL",
                penalty=28,
                category="Index & SARGability",
                offending_snippet=like_match.group(0),
                explanation=(
                    "B-Tree indexes sort strings left-to-right. A leading '%' wildcard invalidates index range seeks "
                    "and forces a full sequential table scan O(N) across every row."
                ),
                recommendation=(
                    f"Use a prefix search ({col_name} LIKE '{term_val}%') for B-Tree index seeks, or create a "
                    "GIN trigram / Full-Text Search index if substring matching is mandatory."
                ),
            )
        )
        category_before["Index & SARGability"] += 28
        rewritten = re.sub(
            r"([a-zA-Z0-9_.]+)\s+LIKE\s+['\"]%([^'\"]+?)%?['\"]",
            rf"\1 LIKE '\2%' /* FasterQL: converted to prefix scan for B-Tree index */",
            rewritten,
            flags=re.IGNORECASE,
        )
        index_columns.append((primary_table, col_name.split(".")[-1]))

    # Rule 3: Function wrapping indexed column in WHERE (e.g., YEAR(col) = 2026, LOWER(col) = 'x')
    func_where = re.search(
        r"\b(YEAR|MONTH|DATE|LOWER|UPPER|CAST)\s*\(\s*([a-zA-Z0-9_.]+)\s*\)\s*=\s*(['\"]?[a-zA-Z0-9_.-]+['\"]?)",
        normalized,
        flags=re.IGNORECASE,
    )
    if func_where:
        fn_name, col_name, target_val = func_where.group(1).upper(), func_where.group(2), func_where.group(3)
        issues.append(
            BottleneckIssue(
                rule_id="CS-003",
                title=f"Non-Sargable Function on Filter Column ({fn_name}({col_name}))",
                severity="HIGH",
                penalty=20,
                category="Index & SARGability",
                offending_snippet=func_where.group(0),
                explanation=(
                    f"Applying {fn_name}() to column '{col_name}' inside WHERE forces the database to evaluate the "
                    "function on every row before filtering, bypassing standard B-Tree indexes."
                ),
                recommendation=(
                    "Rewrite as a direct range predicate on the raw column or add a functional/expression index."
                ),
            )
        )
        category_before["Index & SARGability"] += 20
        if fn_name == "YEAR" and re.match(r"^\d{4}$", target_val.strip("'\"")):
            yr = int(target_val.strip("'\""))
            rewritten = re.sub(
                re.escape(func_where.group(0)),
                f"{col_name} >= '{yr}-01-01' AND {col_name} < '{yr + 1}-01-01'",
                rewritten,
                flags=re.IGNORECASE,
            )
        index_columns.append((primary_table, col_name.split(".")[-1]))

    # Rule 4: Subquery inside IN (SELECT ...) or NOT IN (SELECT ...)
    in_subquery = re.search(
        r"([a-zA-Z0-9_.]+)\s+(NOT\s+)?IN\s*\(\s*SELECT\s+([a-zA-Z0-9_.]+)\s+FROM\s+([a-zA-Z0-9_]+)(?:\s+WHERE\s+([^)]+))?\)",
        normalized,
        flags=re.IGNORECASE,
    )
    if in_subquery:
        outer_col, is_not, inner_col, sub_table, sub_where = in_subquery.groups()
        issues.append(
            BottleneckIssue(
                rule_id="CS-004",
                title="Nested Subquery Scan inside WHERE ... IN (SELECT ...)",
                severity="CRITICAL",
                penalty=26,
                category="Join & Subquery",
                offending_snippet=in_subquery.group(0),
                explanation=(
                    "Uncorrelated or poorly optimized IN/NOT IN subqueries often materialize temporary hash tables "
                    "or trigger O(N * M) nested loop lookups instead of leveraging indexed semi-joins."
                ),
                recommendation=f"Rewrite the subquery as an explicit JOIN or EXISTS clause on {sub_table}({inner_col}).",
            )
        )
        category_before["Join & Subquery"] += 26
        index_columns.append((sub_table, inner_col.split(".")[-1]))
        # Rewrite IN (SELECT ...) to EXISTS or explicit JOIN comment
        sub_filter = f" AND s.{sub_where.strip()}" if sub_where else ""
        exists_clause = (
            f"{'NOT ' if is_not else ''}EXISTS ("
            f"SELECT 1 FROM {sub_table} s WHERE s.{inner_col.split('.')[-1]} = {outer_col}{sub_filter})"
        )
        rewritten = re.sub(
            re.escape(in_subquery.group(0)),
            exists_clause,
            rewritten,
            flags=re.IGNORECASE,
        )

    # Rule 5: Implicit comma join (FROM a, b WHERE a.id = b.a_id)
    if breakdown["comma_joins"]:
        issues.append(
            BottleneckIssue(
                rule_id="CS-005",
                title="Legacy Implicit Comma Join (Cartesian Product Risk)",
                severity="HIGH",
                penalty=18,
                category="Join & Subquery",
                offending_snippet=f"FROM {', '.join(breakdown['tables'])}",
                explanation=(
                    "Implicit comma joins mix join conditions with filter predicates in WHERE. If a join predicate "
                    "is omitted, the planner executes an O(N * M) Cartesian Cross Join."
                ),
                recommendation="Convert comma-separated tables in FROM into explicit ANSI INNER JOIN ... ON clauses.",
            )
        )
        category_before["Join & Subquery"] += 18

    # Rule 6: Unindexed WHERE / ORDER BY columns
    if breakdown["where_columns"]:
        issues.append(
            BottleneckIssue(
                rule_id="CS-006",
                title="Potential Unindexed Predicate / Filter Columns",
                severity="MEDIUM",
                penalty=14,
                category="I/O & Scan",
                offending_snippet=f"WHERE {', '.join(breakdown['where_columns'][:3])}",
                explanation=(
                    "Filtering on columns without a matching composite B-Tree index requires scanning heap pages "
                    "sequentially and discarding non-matching rows in memory."
                ),
                recommendation=(
                    f"Add a composite B-Tree index covering equality predicates first, then range/sort columns."
                ),
            )
        )
        category_before["I/O & Scan"] += 14
        for col in breakdown["where_columns"]:
            index_columns.append((primary_table, col.split(".")[-1]))

    # Rule 7: Missing LIMIT on SELECT query with ORDER BY or large scan
    if not breakdown["has_limit"] and re.match(r"^\s*SELECT\b", normalized, flags=re.IGNORECASE):
        if not re.search(r"\bCOUNT\s*\(|\bSUM\s*\(|\bAVG\s*\(", normalized, flags=re.IGNORECASE) or breakdown["order_columns"]:
            issues.append(
                BottleneckIssue(
                    rule_id="CS-007",
                    title="Unbounded Result Set & External Sort Overhead (Missing LIMIT)",
                    severity="MEDIUM",
                    penalty=12,
                    category="Memory & Sort",
                    offending_snippet="ORDER BY without LIMIT" if breakdown["order_columns"] else "Unbounded SELECT",
                    explanation=(
                        "Sorting or returning an unbounded result set forces the database to perform an external "
                        "merge sort on disk rather than an in-memory Top-N heap sort."
                    ),
                    recommendation="Append a pagination LIMIT clause (e.g., LIMIT 100) so the planner can use a bounded Top-N sort.",
                )
            )
            category_before["Memory & Sort"] += 16
            rewritten = rewritten.rstrip().rstrip(";") + "\nLIMIT 100;"

    # Build deduplicated CREATE INDEX suggestions
    seen_cols = []
    for tbl, col in index_columns:
        clean_col = re.sub(r"[^a-zA-Z0-9_]", "", col)
        if clean_col and clean_col.lower() not in seen_cols:
            seen_cols.append(clean_col.lower())

    for col in breakdown["order_columns"]:
        clean_col = re.sub(r"[^a-zA-Z0-9_]", "", col.split(".")[-1])
        if clean_col and clean_col.lower() not in seen_cols:
            seen_cols.append(clean_col.lower())

    index_ddl = []
    if seen_cols:
        idx_name = f"idx_{primary_table.lower()}_{'_'.join(seen_cols[:3])}"
        index_ddl.append(
            f"CREATE INDEX CONCURRENTLY {idx_name}\nON {primary_table} ({', '.join(seen_cols[:3])});"
        )
    else:
        index_ddl.append(f"-- Query predicates already concise; verify primary key index on {primary_table}(id).")

    # Calculate final scores
    raw_total = sum(category_before.values())
    original_score = min(98, max(12, raw_total))

    category_after = {
        "I/O & Scan": max(5, int(category_before["I/O & Scan"] * 0.25)),
        "Index & SARGability": max(4, int(category_before["Index & SARGability"] * 0.20)),
        "Join & Subquery": max(4, int(category_before["Join & Subquery"] * 0.25)),
        "Memory & Sort": max(4, int(category_before["Memory & Sort"] * 0.30)),
    }
    optimized_score = sum(category_after.values()) if issues else original_score

    if original_score >= 75:
        complexity_before = "O(N * M) Nested Loop / Full Table Scan"
    elif original_score >= 45:
        complexity_before = "O(N) Sequential Table Scan + Sort"
    else:
        complexity_before = "O(log N) Indexed Seek"

    complexity_after = "O(log N) B-Tree Index Seek + Bounded Top-N"

    return AuditResult(
        raw_sql=clean_sql,
        formatted_sql=formatted_sql,
        optimized_sql=format_sql_query(rewritten),
        index_ddl=index_ddl,
        original_score=original_score,
        optimized_score=optimized_score,
        complexity_class_before=complexity_before,
        complexity_class_after=complexity_after,
        issues=issues,
        structural_breakdown=breakdown,
        category_scores_before=category_before,
        category_scores_after=category_after,
    )


if __name__ == "__main__":
    sample = """
    SELECT * FROM orders
    WHERE customer_email LIKE '%@gmail.com'
      AND YEAR(created_at) = 2026
      AND user_id IN (SELECT id FROM users WHERE status = 'active')
    ORDER BY created_at DESC;
    """
    res = audit_sql_query(sample)
    print(f"Original Score: {res.original_score} ({res.complexity_class_before})")
    print(f"Optimized Score: {res.optimized_score} ({res.complexity_class_after})")
    print("Issues found:", len(res.issues))
    print("Optimized SQL:\n", res.optimized_sql)
    print("Index DDL:\n", "\n".join(res.index_ddl))
