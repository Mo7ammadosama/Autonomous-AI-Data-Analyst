"""
NL2SQL Service — Natural Language to SQL with automatic execution and visualization.

Architecture:
  1. Schema-aware SQL generation via LLM
  2. SQL safety validation (whitelist SELECT-only)
  3. In-memory SQLite execution on the DataFrame
  4. Auto chart generation for the result
  5. Audit log stored in NL2SQLQuery table
"""

import re
import time
import logging
import sqlite3
import json
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Forbidden SQL keywords (injection + write protection) ──────
_FORBIDDEN_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|EXECUTE|"
    r"PRAGMA|ATTACH|DETACH|LOAD_EXTENSION|SHELL|SYSTEM)\b",
    re.IGNORECASE,
)

_VALID_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def validate_sql(sql: str) -> Tuple[bool, str]:
    """Return (is_safe, reason). Only SELECT / WITH queries are allowed."""
    if not _VALID_START.match(sql):
        return False, "Only SELECT queries are allowed."
    if _FORBIDDEN_PATTERNS.search(sql):
        match = _FORBIDDEN_PATTERNS.search(sql).group()
        return False, f"Forbidden keyword detected: {match}"
    if ";" in sql[sql.index("SELECT") + 6 :]:
        # Multiple statements separated by semicolon
        return False, "Multiple SQL statements are not allowed."
    return True, ""


def df_to_sqlite(df: pd.DataFrame, table_name: str = "data") -> sqlite3.Connection:
    """Load a DataFrame into an in-memory SQLite database for SQL execution."""
    conn = sqlite3.connect(":memory:")
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    return conn


def execute_sql_on_df(
    df: pd.DataFrame, sql: str, table_name: str = "data"
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Execute a validated SQL query against the DataFrame in SQLite.
    Returns (result_df, error_message).
    """
    # Replace common references to the table name
    sql_normalized = re.sub(
        r"\bfrom\s+(table|df|dataset|data_table)\b",
        f"FROM {table_name}",
        sql,
        flags=re.IGNORECASE,
    )
    # If no FROM clause refers to an explicit table name, inject it
    if re.search(r"\bFROM\s+\w+", sql_normalized, re.IGNORECASE) is None:
        # Append table after SELECT ... (no FROM)
        sql_normalized = sql_normalized.rstrip(";")
        sql_normalized += f" FROM {table_name}"

    conn = df_to_sqlite(df, table_name)
    try:
        result = pd.read_sql_query(sql_normalized, conn)
        return result, None
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()


def build_schema_context(df: pd.DataFrame, max_rows: int = 3) -> str:
    """Create a compact schema description for the LLM prompt."""
    lines = [f"Table name: data", f"Rows: {len(df):,}  Columns: {len(df.columns)}", ""]
    for col in df.columns:
        dtype = str(df[col].dtype)
        nulls = df[col].isna().sum()
        if df[col].dtype in [object, "string"]:
            sample = df[col].dropna().head(3).tolist()
            lines.append(f"  - {col} (TEXT, {nulls} nulls) sample: {sample}")
        elif "datetime" in dtype:
            mn, mx = df[col].min(), df[col].max()
            lines.append(f"  - {col} (DATETIME) range: {mn} → {mx}")
        else:
            mn, mx, mean = df[col].min(), df[col].max(), df[col].mean()
            lines.append(f"  - {col} (NUMERIC, {nulls} nulls) min={mn:.2g} max={mx:.2g} avg={mean:.2g}")
    return "\n".join(lines)


def auto_chart_for_result(result_df: pd.DataFrame, question: str) -> Optional[Dict]:
    """Generate a Plotly chart spec from SQL result automatically."""
    if result_df is None or result_df.empty:
        return None
    try:
        import plotly.express as px

        num_cols = result_df.select_dtypes(include="number").columns.tolist()
        str_cols = result_df.select_dtypes(include="object").columns.tolist()

        if len(result_df.columns) == 2 and len(str_cols) == 1 and len(num_cols) == 1:
            # Classic category → value bar chart
            fig = px.bar(result_df, x=str_cols[0], y=num_cols[0],
                         title=question[:80], template="plotly_dark")
            return json.loads(fig.to_json())

        if len(num_cols) >= 2:
            fig = px.scatter(result_df, x=num_cols[0], y=num_cols[1],
                             title=question[:80], template="plotly_dark")
            return json.loads(fig.to_json())

        if len(num_cols) == 1:
            fig = px.histogram(result_df, x=num_cols[0],
                               title=question[:80], template="plotly_dark")
            return json.loads(fig.to_json())
    except Exception as e:
        logger.debug(f"Auto chart generation failed: {e}")
    return None


class NL2SQLService:
    """
    Converts natural language questions into SQL, executes them,
    and returns structured results with optional visualizations.
    """

    SYSTEM_PROMPT = """You are a SQL expert. Given a dataset schema and a user question,
generate a single valid SQLite SELECT query that answers the question.

Rules:
- The table name is always: data
- Output ONLY the SQL query — no explanation, no markdown, no backticks
- Use standard SQLite syntax
- Always use column names exactly as shown in the schema (case-sensitive)
- For aggregations use aliases: SELECT col AS label, SUM(val) AS total
- Never use INSERT, UPDATE, DELETE, DROP or any write operations
- Limit results to 1000 rows unless the user asks for all data

Examples:
  Question: "Show top 5 countries by total sales"
  SQL: SELECT country, SUM(sales) AS total_sales FROM data GROUP BY country ORDER BY total_sales DESC LIMIT 5

  Question: "What is the average age by gender?"
  SQL: SELECT gender, AVG(age) AS avg_age FROM data GROUP BY gender ORDER BY avg_age DESC
"""

    def __init__(self, llm_service):
        self.llm = llm_service

    def generate_sql(self, question: str, schema_context: str) -> str:
        """Use LLM to generate SQL, with rule-based fallback when no LLM is configured."""
        user_prompt = f"""Schema:
{schema_context}

Question: {question}

SQL query:"""
        raw = self.llm.complete(self.SYSTEM_PROMPT, user_prompt, max_tokens=300)
        sql = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE).strip().rstrip("```").strip()
        # If LLM returned a non-SQL placeholder, fall back to rule-based generation
        if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            sql = self._rule_based_sql(question, schema_context)
        return sql

    def _rule_based_sql(self, question: str, schema_context: str) -> str:
        """Generate SQL from natural language patterns without an LLM."""
        q = question.lower().strip()
        tbl = "data"

        # Extract column names from schema context
        cols = re.findall(r"- (\w+) \(", schema_context)
        num_cols = [c for c in cols if re.search(
            rf"- {re.escape(c)} \((NUMERIC|INT|FLOAT|DOUBLE|REAL)",
            schema_context, re.IGNORECASE)]
        cat_cols = [c for c in cols if re.search(
            rf"- {re.escape(c)} \((TEXT|VARCHAR|STRING|CHAR)",
            schema_context, re.IGNORECASE)]
        date_cols = [c for c in cols if re.search(
            rf"- {re.escape(c)} \((DATETIME|DATE|TIMESTAMP)",
            schema_context, re.IGNORECASE)]

        first_num = num_cols[0] if num_cols else (cols[1] if len(cols) > 1 else None)
        first_cat = cat_cols[0] if cat_cols else None
        first_date = date_cols[0] if date_cols else None

        # Count
        if re.search(r"\bhow many\b|\bcount\b|\bnumber of\b|\btotal rows?\b", q):
            if first_cat and re.search(r"\bby\b|\bper\b|\beach\b", q):
                return f"SELECT {first_cat}, COUNT(*) AS count FROM {tbl} GROUP BY {first_cat} ORDER BY count DESC LIMIT 20"
            return f"SELECT COUNT(*) AS total_rows FROM {tbl}"

        # Sum / total
        if re.search(r"\btotal\b|\bsum\b", q):
            col = first_num or "1"
            if first_cat and re.search(r"\bby\b|\bper\b|\beach\b|\bgroup\b", q):
                return f"SELECT {first_cat}, SUM({col}) AS total_{col} FROM {tbl} GROUP BY {first_cat} ORDER BY total_{col} DESC LIMIT 20"
            return f"SELECT SUM({col}) AS total_{col} FROM {tbl}"

        # Average
        if re.search(r"\baverage\b|\bavg\b|\bmean\b", q):
            col = first_num or "1"
            if first_cat and re.search(r"\bby\b|\bper\b|\beach\b", q):
                return f"SELECT {first_cat}, AVG({col}) AS avg_{col} FROM {tbl} GROUP BY {first_cat} ORDER BY avg_{col} DESC LIMIT 20"
            return f"SELECT AVG({col}) AS avg_{col} FROM {tbl}"

        # Top N / highest / max
        if re.search(r"\btop\b|\bhighest\b|\bmaximum\b|\bmax\b\b", q):
            col = first_num or (cols[0] if cols else "*")
            m = re.search(r"\btop\s+(\d+)\b", q)
            n = m.group(1) if m else "10"
            if first_cat:
                return (f"SELECT {first_cat}, SUM({col}) AS total_{col} FROM {tbl} "
                        f"GROUP BY {first_cat} ORDER BY total_{col} DESC LIMIT {n}")
            return f"SELECT * FROM {tbl} ORDER BY {col} DESC LIMIT {n}"

        # Bottom N / lowest / min
        if re.search(r"\bbottom\b|\blowest\b|\bminimum\b|\bmin\b", q):
            col = first_num or (cols[0] if cols else "*")
            return f"SELECT * FROM {tbl} ORDER BY {col} ASC LIMIT 10"

        # Trend over time
        if re.search(r"\btrend\b|\bover time\b|\bmonthly\b|\bdaily\b|\bweekly\b", q):
            if first_date and first_num:
                return (f"SELECT {first_date}, SUM({first_num}) AS total_{first_num} "
                        f"FROM {tbl} GROUP BY {first_date} ORDER BY {first_date} ASC LIMIT 100")

        # Group / breakdown / distribution
        if re.search(r"\bdistribution\b|\bbreakdown\b|\bby\b|\bgroup\b", q) and first_cat:
            agg = f"SUM({first_num})" if first_num else "COUNT(*)"
            alias = f"total_{first_num}" if first_num else "count"
            return f"SELECT {first_cat}, {agg} AS {alias} FROM {tbl} GROUP BY {first_cat} ORDER BY {alias} DESC LIMIT 20"

        # Unique / distinct values
        if re.search(r"\bunique\b|\bdistinct\b|\bdifferent\b", q) and first_cat:
            return f"SELECT DISTINCT {first_cat} FROM {tbl} ORDER BY {first_cat} LIMIT 50"

        # Show / list / all
        if re.search(r"\bshow\b|\blist\b|\bsee\b|\ball\b|\bdisplay\b", q):
            return f"SELECT * FROM {tbl} LIMIT 100"

        # Default: show everything
        return f"SELECT * FROM {tbl} LIMIT 100"

    def run(
        self,
        question: str,
        df: pd.DataFrame,
        dataset_name: str = "dataset",
    ) -> Dict[str, Any]:
        """
        Full pipeline: question → SQL → execute → visualize.

        Returns a dict with:
          - question (str)
          - sql (str)
          - data (list[dict]) — result rows
          - columns (list[str])
          - row_count (int)
          - chart (dict | None) — Plotly chart spec
          - error (str | None)
          - execution_time_ms (int)
        """
        t0 = time.time()

        schema = build_schema_context(df)
        sql = self.generate_sql(question, schema)
        logger.info(f"NL2SQL generated: {sql[:200]}")

        is_safe, reason = validate_sql(sql)
        if not is_safe:
            return {
                "question": question,
                "sql": sql,
                "data": [],
                "columns": [],
                "row_count": 0,
                "chart": None,
                "error": f"SQL safety check failed: {reason}",
                "execution_time_ms": int((time.time() - t0) * 1000),
            }

        result_df, error = execute_sql_on_df(df, sql)
        elapsed_ms = int((time.time() - t0) * 1000)

        if error:
            # Attempt to self-correct with the error feedback
            logger.warning(f"NL2SQL execution error: {error} — attempting correction")
            corrected_sql = self._correct_sql(question, schema, sql, error)
            result_df, error2 = execute_sql_on_df(df, corrected_sql)
            if error2 is None:
                sql = corrected_sql
                error = None
            else:
                error = error2

        chart = None
        rows = []
        columns = []
        row_count = 0

        if result_df is not None and not result_df.empty:
            # Convert NaN → None for JSON serialization
            result_clean = result_df.where(pd.notna(result_df), None)
            rows = result_clean.head(500).to_dict("records")
            columns = result_df.columns.tolist()
            row_count = len(result_df)
            chart = auto_chart_for_result(result_df.head(100), question)

        return {
            "question": question,
            "sql": sql,
            "data": rows,
            "columns": columns,
            "row_count": row_count,
            "chart": chart,
            "error": error,
            "execution_time_ms": elapsed_ms,
        }

    def _correct_sql(
        self, question: str, schema: str, bad_sql: str, error: str
    ) -> str:
        """Self-correction: feed the error back to LLM for a revised query."""
        user_prompt = f"""Schema:
{schema}

Question: {question}

The following SQL query produced an error:
{bad_sql}

Error: {error}

Please write a corrected SQLite SELECT query. Output ONLY the SQL, no explanation."""
        raw = self.llm.complete(self.SYSTEM_PROMPT, user_prompt, max_tokens=300)
        sql = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE).strip().rstrip("```").strip()
        return sql
