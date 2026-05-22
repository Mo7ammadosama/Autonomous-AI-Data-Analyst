"""
DataAnalystAgent — ReAct (Reason + Act) loop for autonomous data analysis.

Loop: Plan → Think → Select Tool → Execute → Observe → Iterate → Final Answer
Max iterations: 15. Terminates early on final_answer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "ollama")

# ─────────────────────────────────────────────────────────────────────────────
#  Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentStep:
    iteration: int
    thought: str
    action: str          # tool name
    action_input: dict
    observation: str
    figures: list[str] = field(default_factory=list)   # base64 PNGs from sandbox
    error: bool = False


@dataclass
class AgentResult:
    run_id: str
    status: str          # completed | failed
    steps: list[AgentStep]
    summary: str
    charts: list[dict]   # [{title, base64}]
    token_usage: int
    duration_seconds: float


# ─────────────────────────────────────────────────────────────────────────────
#  JSON parser (robust — handles markdown fences and extra text)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_llm_response(raw: str) -> dict:
    """Parse LLM response as JSON, handling common formatting issues.

    Handles:
    - Markdown code fences: ```json ... ``` or ``` ... ```
    - Extra text before the first { or after the last }
    - Regex fallback to extract action/thought if JSON is still invalid
    """
    text = raw.strip()

    # 1. Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # 2. Extract the outermost JSON object (first { … last })
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace : last_brace + 1]

    # 3. Try standard JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 4. Regex fallback — extract thought and action at minimum
    thought_match = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)
    # Try to pull action_input as a sub-object
    action_input: dict = {}
    ai_match = re.search(r'"action_input"\s*:\s*(\{.*?\})', text, re.DOTALL)
    if ai_match:
        try:
            action_input = json.loads(ai_match.group(1))
        except json.JSONDecodeError:
            pass

    if action_match:
        return {
            "thought": thought_match.group(1) if thought_match else "(parse fallback)",
            "action": action_match.group(1),
            "action_input": action_input,
        }

    raise json.JSONDecodeError("Could not extract valid JSON or action from LLM response", text, 0)


# ─────────────────────────────────────────────────────────────────────────────
#  System prompt
# ─────────────────────────────────────────────────────────────────────────────

# Use str.replace() for substitution to avoid f-string brace-escaping issues
# with JSON example blocks that contain many literal { } characters.
_SYSTEM_PROMPT_TEMPLATE = """\
You are DataMind, a senior McKinsey Partner-level AI data analyst. Today is {current_date}.

IDENTITY: You think and communicate like a top-tier management consultant, not a data scientist.
Every number you surface has a dollar sign attached. Every finding has a decision attached.
You replace 3 data analysts at $150K/year each.

MANDATORY ANALYSIS PROTOCOL:
1. START every final answer with a "CEO Briefing" — exactly 2 sentences any CEO understands immediately
2. Use BUSINESS language only: "Revenue declined 12% YoY" not "column sum decreased"
3. Generate MINIMUM 3 charts: trend line + breakdown + comparison
4. Always include a "Risk Matrix" — quantify the financial consequence of inaction
5. Always quantify impact with dollar amounts: "~$2.3M revenue risk if unaddressed"
6. End with a structured "30-60-90 Day Action Plan" with specific, named actions
7. Self-verify all numbers before presenting — cross-check your own computations
8. Auto-detect user language → respond in Arabic or English accordingly
9. Think like you are presenting to a board of directors

At each step output EXACTLY this JSON (nothing else, no markdown fences):
{"thought": "your McKinsey-level reasoning", "action": "tool_name", "action_input": {}}

When analysis is complete, output:
{"thought": "complete synthesis of findings", "action": "final_answer", "action_input": {
  "ceo_briefing": "2 sentences any CEO understands. Include the single most important number.",
  "executive_summary": "3-4 sentence board-level narrative with business context",
  "key_findings": [
    "Finding with specific $ or % number and business implication",
    "Finding with quantified impact",
    "Finding with actionable insight"
  ],
  "risk_matrix": {
    "immediate_risk": "Financial impact in next 30 days if no action",
    "quarterly_risk": "Financial impact in next quarter",
    "annual_risk": "Annualized financial exposure"
  },
  "recommendations": [
    {"action": "Specific named action", "priority": "high", "expected_impact": "Quantified dollar or % result", "timeline": "30 days"},
    {"action": "Specific named action", "priority": "medium", "expected_impact": "Quantified result", "timeline": "60 days"},
    {"action": "Specific named action", "priority": "low", "expected_impact": "Quantified result", "timeline": "90 days"}
  ],
  "action_plan": {
    "days_1_30": "Immediate high-impact actions with named owners",
    "days_31_60": "Mid-term structural changes",
    "days_61_90": "Strategic initiatives and measurement framework"
  },
  "confidence": "high|medium|low",
  "data_quality_notes": "Any caveats about data completeness"
}}

Available tools: assess_data_quality, clean_data, run_eda, detect_anomalies_advanced, execute_python, execute_sql, get_dataset_info, get_column_stats, auto_visualize, write_report_section, benchmark_industry, generate_action_plan, final_answer

Tool usage:
- assess_data_quality: {"dataset_id": "<id>"}
- clean_data: {"dataset_id": "<id>", "strategy": "auto"}
- run_eda: {"dataset_id": "<id>"}
- detect_anomalies_advanced: {"dataset_id": "<id>", "columns": ["col1", "col2"]}
- get_dataset_info: {"dataset_id": "<id>"}
- get_column_stats: {"dataset_id": "<id>", "columns": ["col1"]}
- execute_python: {"code": "<pandas/numpy/scipy/plotly code>", "dataset_id": "<id>"}
- execute_sql: {"query": "<SQL SELECT only>", "connection_id": null}
- auto_visualize: {"dataset_id": "<id>", "chart_type": "bar|line|scatter|histogram|pie|heatmap|box", "x_col": "<col>", "y_col": "<col>", "title": "<title>"}
- write_report_section: {"section": "<name>", "content": "<markdown>"}
- benchmark_industry: {"metric_name": "<metric>", "your_value": <number>, "industry": "<retail|finance|healthcare|saas|manufacturing>"}
- generate_action_plan: {"findings": ["finding1", "finding2"], "priority_area": "<area>", "budget_context": "<available|constrained|unknown>"}
- final_answer: see structured format above

MANDATORY 8-Step Data Analyst Workflow (follow in order when a dataset is provided):
1. assess_data_quality — always first; identify data issues before any analysis
2. clean_data — fix nulls, duplicates, whitespace; use strategy="auto"
3. run_eda — full exploratory analysis: distributions, correlations, outliers
4. detect_anomalies_advanced — flag statistical anomalies with business impact
5. execute_python / get_column_stats — deep-dive analysis on specific questions
6. auto_visualize — generate 3+ charts (trend, breakdown, comparison minimum)
7. benchmark_industry — compare key metrics against industry benchmarks
8. generate_action_plan → final_answer — structured McKinsey-style roadmap

Execution Rules:
- ALWAYS follow the 8-step workflow above when a dataset_id is provided
- Generate EXACTLY 3+ charts (trend, breakdown, comparison minimum)
- ALWAYS run benchmark_industry for key metrics
- ALWAYS call generate_action_plan before final_answer
- Every number needs dollar/percentage business context
- Max 12 iterations — be thorough but efficient

{memory_block}"""


def _build_system_prompt(memory_block: str = "") -> str:
    """Build the system prompt injecting current date and user memory block."""
    current_date = datetime.now().strftime("%A, %B %d, %Y %H:%M")
    mem = (
        f"=== USER CONTEXT ===\n{memory_block}\n==================================="
        if memory_block
        else ""
    )
    return (
        _SYSTEM_PROMPT_TEMPLATE
        .replace("{current_date}", current_date)
        .replace("{memory_block}", mem)
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Tool implementations
# ─────────────────────────────────────────────────────────────────────────────

def _tool_get_dataset_info(dataset_id: str, db: Session) -> str:
    """Return schema, dtypes, and 3-row sample."""
    try:
        from models.database import Dataset
        import pandas as pd

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found."

        file_path = dataset.file_path
        if not os.path.exists(file_path):
            return f"File not found at {file_path}."

        df = pd.read_csv(file_path, nrows=5)
        info = {
            "name": dataset.name,
            "rows": dataset.row_count,
            "columns": dataset.column_count,
            "dtypes": df.dtypes.astype(str).to_dict(),
            "sample": df.head(3).to_dict(orient="records"),
            "columns_list": df.columns.tolist(),
        }
        return json.dumps(info, default=str, indent=2)
    except Exception as exc:
        return f"Error reading dataset: {exc}"


def _tool_get_column_stats(dataset_id: str, columns: list[str], db: Session) -> str:
    """Return descriptive statistics for requested columns."""
    try:
        from models.database import Dataset
        import pandas as pd

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found."

        df = pd.read_csv(dataset.file_path, usecols=columns)
        stats = df.describe(include="all").to_dict()
        return json.dumps(stats, default=str, indent=2)
    except Exception as exc:
        return f"Error computing stats: {exc}"


def _tool_execute_python(code: str, dataset_id: Optional[str], db: Session) -> tuple[str, list[str]]:
    """Run Python in sandbox; return (observation_text, [base64_figures])."""
    from services.sandbox import PythonSandbox
    from models.database import Dataset
    import pandas as pd

    df_csv = None
    if dataset_id:
        try:
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if dataset and os.path.exists(dataset.file_path):
                df = pd.read_csv(dataset.file_path)
                df_csv = df.to_csv(index=False)
        except Exception as exc:
            logger.warning(f"Could not pre-load dataset for sandbox: {exc}")

    sandbox = PythonSandbox(timeout=30)
    result = sandbox.execute(code, df_csv=df_csv)

    if result.blocked:
        return f"BLOCKED: {result.block_reason}", []
    if result.timed_out:
        return "TIMEOUT: code exceeded 30-second limit", []

    parts = []
    if result.output:
        parts.append(result.output[:3000])
    if result.dataframe_html:
        parts.append("[DataFrame preview captured]")
    if result.error:
        parts.append(f"ERROR:\n{result.error[:2000]}")
    observation = "\n".join(parts) or "(no output)"
    return observation, result.figures


def _tool_execute_sql(query: str, connection_id: Optional[str], db: Session) -> str:
    """Execute SQL against a connected DB or the analysis DB."""
    try:
        import pandas as pd
        from models.database import DataConnection

        if connection_id:
            conn_rec = db.query(DataConnection).filter(DataConnection.id == connection_id).first()
            if not conn_rec:
                return f"Connection {connection_id} not found."
            from sqlalchemy import create_engine, text
            eng = create_engine(conn_rec.connection_string)
            with eng.connect() as con:
                result = con.execute(text(query))
                rows = result.fetchmany(100)
                cols = list(result.keys())
            df = pd.DataFrame(rows, columns=cols)
        else:
            from models.database import engine as app_engine
            from sqlalchemy import text
            with app_engine.connect() as con:
                result = con.execute(text(query))
                rows = result.fetchmany(100)
                cols = list(result.keys())
            df = pd.DataFrame(rows, columns=cols)

        return df.to_string(index=False, max_rows=30)
    except Exception as exc:
        return f"SQL error: {exc}"


def _tool_search_web(query: str) -> str:
    """Search the web using DuckDuckGo — no API key required."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(f"**{r.get('title', '')}**\n{r.get('body', '')}\nSource: {r.get('href', '')}\n")
        return "\n---\n".join(lines)
    except Exception as exc:
        return f"Web search error: {exc}"


def _tool_search_domain_template(domain: str, task_type: str) -> str:
    from services.domain_templates import get_template
    template = get_template(domain, task_type)
    if not template:
        return f"No template found for domain={domain} task_type={task_type}"
    return json.dumps(template, indent=2)


def _tool_auto_visualize(
    dataset_id: str,
    chart_type: str,
    x_col: str,
    y_col: Optional[str],
    title: str,
    db: Session,
) -> tuple[str, list[str]]:
    """Generate a Plotly chart without user-written code."""
    try:
        from models.database import Dataset
        import pandas as pd
        import plotly.express as px
        import io, base64

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found.", []
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found.", []

        df = pd.read_csv(dataset.file_path)

        chart_type = chart_type.lower()
        if chart_type == "bar":
            fig = px.bar(df, x=x_col, y=y_col, title=title)
        elif chart_type == "line":
            fig = px.line(df, x=x_col, y=y_col, title=title)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_col, y=y_col, title=title)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x_col, title=title)
        elif chart_type == "box":
            fig = px.box(df, x=x_col, y=y_col, title=title)
        elif chart_type == "pie":
            fig = px.pie(df, names=x_col, values=y_col, title=title)
        elif chart_type == "heatmap":
            numeric_df = df.select_dtypes(include="number")
            fig = px.imshow(numeric_df.corr(), title=title)
        else:
            return f"Unknown chart_type: {chart_type}. Use bar|line|scatter|histogram|box|pie|heatmap.", []

        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        try:
            img_bytes = fig.to_image(format="png", width=900, height=500)
        except Exception:
            img_bytes = None
        if img_bytes:
            b64 = base64.b64encode(img_bytes).decode()
            return f"Chart '{title}' generated successfully.", [b64]
        return f"Chart '{title}' generated successfully (image export unavailable).", []
    except Exception as exc:
        return f"auto_visualize error: {exc}", []


def _tool_compare_periods(
    dataset_id: str,
    date_column: str,
    metric_column: str,
    period1: str,
    period2: str,
    db: Session,
) -> str:
    """Compare a metric between two periods; periods may be YYYY-MM, YYYY-QN, or YYYY."""
    try:
        from models.database import Dataset
        import pandas as pd
        import numpy as np

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found."
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found."

        df = pd.read_csv(dataset.file_path)

        if date_column not in df.columns:
            return f"Column '{date_column}' not found. Available: {df.columns.tolist()}"
        if metric_column not in df.columns:
            return f"Column '{metric_column}' not found. Available: {df.columns.tolist()}"

        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
        df = df.dropna(subset=[date_column])
        df[metric_column] = pd.to_numeric(df[metric_column], errors="coerce")

        def _matches_period(series: "pd.Series[Any]", period: str) -> "pd.Series[Any]":
            p = period.strip().upper()
            # YYYY-QN format
            if re.match(r"^\d{4}-Q[1-4]$", p):
                year, q = int(p[:4]), int(p[-1])
                q_start_month = (q - 1) * 3 + 1
                return (series.dt.year == year) & (series.dt.quarter == q)
            # YYYY-MM format
            if re.match(r"^\d{4}-\d{2}$", p):
                year, month = int(p[:4]), int(p[5:])
                return (series.dt.year == year) & (series.dt.month == month)
            # YYYY format
            if re.match(r"^\d{4}$", p):
                return series.dt.year == int(p)
            # Fallback: string match on date string
            return series.dt.strftime("%Y-%m-%d").str.startswith(period)

        df1 = df[_matches_period(df[date_column], period1)][metric_column].dropna()
        df2 = df[_matches_period(df[date_column], period2)][metric_column].dropna()

        if df1.empty and df2.empty:
            return f"No rows matched either period ({period1}, {period2}). Check date column format."

        def _stats(s: "pd.Series[Any]") -> dict:
            return {
                "count": int(len(s)),
                "sum": float(round(s.sum(), 4)),
                "mean": float(round(s.mean(), 4)) if len(s) else 0,
                "median": float(round(s.median(), 4)) if len(s) else 0,
            }

        s1, s2 = _stats(df1), _stats(df2)

        def _pct(v1: float, v2: float) -> str:
            if v1 == 0:
                return "N/A (prior period was 0)"
            return f"{round((v2 - v1) / abs(v1) * 100, 2):+.2f}%"

        lines = [
            f"Period comparison: {period1} vs {period2}  |  Metric: {metric_column}",
            "",
            f"{'Metric':<12} {'Period 1 (' + period1 + ')':>20} {'Period 2 (' + period2 + ')':>20} {'Change':>12}",
            "-" * 68,
            f"{'Count':<12} {s1['count']:>20} {s2['count']:>20} {_pct(s1['count'], s2['count']):>12}",
            f"{'Sum':<12} {s1['sum']:>20,.2f} {s2['sum']:>20,.2f} {_pct(s1['sum'], s2['sum']):>12}",
            f"{'Mean':<12} {s1['mean']:>20,.4f} {s2['mean']:>20,.4f} {_pct(s1['mean'], s2['mean']):>12}",
            f"{'Median':<12} {s1['median']:>20,.4f} {s2['median']:>20,.4f} {_pct(s1['median'], s2['median']):>12}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"compare_periods error: {exc}"


def _tool_detect_anomalies(dataset_id: str, columns: list[str], db: Session) -> str:
    """Detect outliers using IQR (1.5×) and Z-score (>3) methods."""
    try:
        from models.database import Dataset
        import pandas as pd
        import numpy as np

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found."
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found."

        df = pd.read_csv(dataset.file_path)

        # If no columns specified, use all numeric columns
        if not columns:
            columns = df.select_dtypes(include="number").columns.tolist()

        results: list[dict] = []
        for col in columns:
            if col not in df.columns:
                results.append({"column": col, "error": "Column not found"})
                continue
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue

            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            iqr = q3 - q1
            iqr_low = q1 - 1.5 * iqr
            iqr_high = q3 + 1.5 * iqr

            mean = float(series.mean())
            std = float(series.std())

            iqr_outliers = df[(df[col].notna()) & (
                (pd.to_numeric(df[col], errors="coerce") < iqr_low) |
                (pd.to_numeric(df[col], errors="coerce") > iqr_high)
            )].index.tolist()

            z_outliers: list[int] = []
            if std > 0:
                z_scores = ((pd.to_numeric(df[col], errors="coerce") - mean) / std).abs()
                z_outliers = df[z_scores > 3].index.tolist()

            all_outlier_idx = sorted(set(iqr_outliers) | set(z_outliers))

            results.append({
                "column": col,
                "q1": round(q1, 4),
                "q3": round(q3, 4),
                "iqr": round(iqr, 4),
                "iqr_bounds": [round(iqr_low, 4), round(iqr_high, 4)],
                "mean": round(mean, 4),
                "std": round(std, 4),
                "iqr_outlier_count": len(iqr_outliers),
                "zscore_outlier_count": len(z_outliers),
                "total_unique_anomalies": len(all_outlier_idx),
                "sample_anomalous_rows": df.loc[all_outlier_idx[:5]].to_dict(orient="records") if all_outlier_idx else [],
            })

        if not results:
            return "No numeric columns found or no anomalies detected."

        output_lines = []
        for r in results:
            if "error" in r:
                output_lines.append(f"[{r['column']}] ERROR: {r['error']}")
                continue
            output_lines.append(
                f"[{r['column']}] IQR bounds: ({r['iqr_bounds'][0]}, {r['iqr_bounds'][1]})  "
                f"| IQR outliers: {r['iqr_outlier_count']}  "
                f"| Z-score >3 outliers: {r['zscore_outlier_count']}  "
                f"| Total anomalies: {r['total_unique_anomalies']}"
            )
            if r["sample_anomalous_rows"]:
                output_lines.append(f"  Sample anomalous rows: {json.dumps(r['sample_anomalous_rows'][:3], default=str)}")

        return "\n".join(output_lines)
    except Exception as exc:
        return f"detect_anomalies error: {exc}"


def _tool_generate_executive_summary(
    findings: list[str],
    recommendations: list[str],
    data_period: str,
) -> str:
    """Format findings and recommendations into a clean executive summary markdown."""
    current_date = datetime.now().strftime("%B %d, %Y")
    lines = [
        "# Executive Summary",
        f"**Analysis Period:** {data_period}  |  **Generated:** {current_date}",
        "",
        "---",
        "",
        "## Key Findings",
    ]
    for i, finding in enumerate(findings, 1):
        lines.append(f"{i}. {finding}")
    lines.extend([
        "",
        "---",
        "",
        "## Recommendations",
    ])
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec}")
    lines.extend([
        "",
        "---",
        "*This executive summary was generated by DataMind AI Analytics Platform.*",
    ])
    return "\n".join(lines)


def _tool_assess_data_quality(dataset_id: str, db: Session) -> str:
    """Step 1 of professional workflow: assess data quality before any analysis."""
    try:
        from models.database import Dataset
        import pandas as pd
        import numpy as np

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found."
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found on disk."

        df = pd.read_csv(dataset.file_path)
        total_rows = len(df)
        total_cols = len(df.columns)
        total_cells = total_rows * total_cols

        issues = []
        col_reports = []
        for col in df.columns:
            missing = int(df[col].isna().sum())
            missing_pct = round(missing / total_rows * 100, 1)
            duplicates = int(df.duplicated().sum())
            unique_count = int(df[col].nunique())
            is_constant = unique_count <= 1
            is_high_cardinality = unique_count / total_rows > 0.95 and total_rows > 50

            col_report = {
                "column": col,
                "dtype": str(df[col].dtype),
                "missing": missing,
                "missing_pct": missing_pct,
                "unique_values": unique_count,
                "is_constant": is_constant,
                "is_likely_id": is_high_cardinality,
            }
            col_reports.append(col_report)

            if missing_pct > 0:
                issues.append(f"MISSING: '{col}' has {missing} nulls ({missing_pct}%)")
            if is_constant:
                issues.append(f"CONSTANT: '{col}' has only 1 unique value — likely useless for analysis")
            if is_high_cardinality:
                issues.append(f"HIGH-CARDINALITY: '{col}' is ~{unique_count} unique across {total_rows} rows — likely an ID column")

        dup_count = int(df.duplicated().sum())
        if dup_count > 0:
            issues.append(f"DUPLICATES: {dup_count} exact duplicate rows ({round(dup_count/total_rows*100,1)}%)")

        quality_score = max(0, 100 - len(issues) * 5 - (dup_count / max(total_rows, 1)) * 50)

        report = {
            "dataset": dataset.name,
            "shape": f"{total_rows:,} rows × {total_cols} columns",
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 2),
            "quality_score": round(quality_score, 1),
            "duplicate_rows": dup_count,
            "issues_found": len(issues),
            "issues": issues,
            "columns": col_reports,
            "recommendation": (
                "Data is clean — proceed to EDA." if not issues
                else f"Found {len(issues)} quality issues. Run clean_data next to fix automatically."
            ),
        }
        return json.dumps(report, default=str, indent=2)
    except Exception as exc:
        return f"assess_data_quality error: {exc}"


def _tool_clean_data(dataset_id: str, strategy: str, db: Session) -> tuple[str, list[str]]:
    """Step 2 of professional workflow: clean the data and log every change."""
    try:
        from models.database import Dataset
        import pandas as pd

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found.", []
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found.", []

        df = pd.read_csv(dataset.file_path)
        original_rows = len(df)
        changelog = []

        # 1. Remove exact duplicates
        dup_count = int(df.duplicated().sum())
        if dup_count > 0:
            df = df.drop_duplicates()
            changelog.append(f"Removed {dup_count} duplicate rows ({round(dup_count/original_rows*100,1)}%)")

        # 2. Fill missing values per column
        for col in df.columns:
            missing = int(df[col].isna().sum())
            if missing == 0:
                continue
            if df[col].dtype in ["float64", "int64", "float32", "int32"]:
                fill_val = df[col].median()
                df[col] = df[col].fillna(fill_val)
                changelog.append(f"Filled {missing} nulls in '{col}' with median {fill_val:.2f}")
            else:
                mode_vals = df[col].mode()
                fill_val = mode_vals.iloc[0] if len(mode_vals) > 0 else "Unknown"
                df[col] = df[col].fillna(fill_val)
                changelog.append(f"Filled {missing} nulls in '{col}' with mode '{fill_val}'")

        # 3. Strip whitespace from string columns
        str_cols = df.select_dtypes(include="object").columns
        for col in str_cols:
            before = df[col].copy()
            df[col] = df[col].str.strip()
            changed = (df[col] != before).sum()
            if changed > 0:
                changelog.append(f"Stripped whitespace from {changed} values in '{col}'")

        # 4. Try to convert date-like string columns to datetime
        for col in str_cols:
            if df[col].dtype == "object":
                sample = df[col].dropna().head(5)
                try:
                    pd.to_datetime(sample, infer_datetime_format=True)
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                    converted = df[col].notna().sum()
                    changelog.append(f"Converted '{col}' to datetime ({converted} values parsed)")
                except Exception:
                    pass

        # Save cleaned file to same path (overwrite)
        df.to_csv(dataset.file_path, index=False)

        # Update dataset metadata
        dataset.row_count = len(df)
        db.commit()

        summary = {
            "original_rows": original_rows,
            "cleaned_rows": len(df),
            "rows_removed": original_rows - len(df),
            "changes_made": len(changelog),
            "changelog": changelog,
            "status": "Dataset cleaned and saved. Ready for analysis.",
        }
        return json.dumps(summary, indent=2), []
    except Exception as exc:
        return f"clean_data error: {exc}", []


def _tool_run_eda(dataset_id: str, db: Session) -> tuple[str, list[str]]:
    """Step 3 of professional workflow: full exploratory data analysis with correlation heatmap."""
    try:
        from models.database import Dataset
        import pandas as pd
        import numpy as np
        import plotly.express as px
        import io
        import base64

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found.", []
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found.", []

        df = pd.read_csv(dataset.file_path)
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        cat_cols = df.select_dtypes(include="object").columns.tolist()
        date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

        eda: dict = {
            "shape": f"{len(df):,} rows × {len(df.columns)} columns",
            "numeric_columns": numeric_cols,
            "categorical_columns": cat_cols,
            "date_columns": date_cols,
            "numeric_stats": {},
            "categorical_stats": {},
            "top_correlations": [],
            "outliers": {},
        }

        # Numeric statistics
        if numeric_cols:
            desc = df[numeric_cols].describe().to_dict()
            for col in numeric_cols:
                s = df[col].dropna()
                skew = float(s.skew()) if len(s) > 2 else 0.0
                kurt = float(s.kurtosis()) if len(s) > 2 else 0.0
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr = q3 - q1
                outlier_mask = (s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)
                outlier_count = int(outlier_mask.sum())
                eda["numeric_stats"][col] = {
                    "mean": round(float(s.mean()), 3),
                    "median": round(float(s.median()), 3),
                    "std": round(float(s.std()), 3),
                    "min": round(float(s.min()), 3),
                    "max": round(float(s.max()), 3),
                    "skewness": round(skew, 2),
                    "kurtosis": round(kurt, 2),
                    "outliers_iqr": outlier_count,
                }
                if outlier_count > 0:
                    eda["outliers"][col] = outlier_count

        # Correlation analysis
        figures = []
        if len(numeric_cols) >= 2:
            corr_matrix = df[numeric_cols].corr()
            pairs = []
            for i in range(len(numeric_cols)):
                for j in range(i + 1, len(numeric_cols)):
                    c1, c2 = numeric_cols[i], numeric_cols[j]
                    corr_val = float(corr_matrix.loc[c1, c2])
                    if not np.isnan(corr_val):
                        pairs.append({"col1": c1, "col2": c2, "correlation": round(corr_val, 3)})
            pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
            eda["top_correlations"] = pairs[:5]

            # Correlation heatmap
            try:
                fig = px.imshow(
                    corr_matrix,
                    title="Correlation Matrix",
                    color_continuous_scale="RdBu_r",
                    zmin=-1, zmax=1,
                    text_auto=".2f",
                )
                fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                img_bytes = fig.to_image(format="png", width=900, height=600)
                figures.append(base64.b64encode(img_bytes).decode())
            except Exception:
                pass

        # Categorical statistics
        for col in cat_cols[:5]:
            vc = df[col].value_counts().head(10)
            eda["categorical_stats"][col] = {
                "unique_values": int(df[col].nunique()),
                "top_values": vc.to_dict(),
            }

        return json.dumps(eda, default=str, indent=2), figures
    except Exception as exc:
        return f"run_eda error: {exc}", []


def _tool_detect_anomalies_advanced(dataset_id: str, columns: list[str], db: Session) -> str:
    """Advanced anomaly detection: Z-score + IQR combined."""
    try:
        from models.database import Dataset
        import pandas as pd
        import numpy as np

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return f"Dataset {dataset_id} not found."
        if not os.path.exists(dataset.file_path):
            return "Dataset file not found."

        df = pd.read_csv(dataset.file_path)
        numeric_cols = columns if columns else df.select_dtypes(include="number").columns.tolist()
        numeric_cols = [c for c in numeric_cols if c in df.columns][:8]

        anomalies = []
        summary = {"columns_analyzed": numeric_cols, "anomalies_by_column": {}}

        for col in numeric_cols:
            s = df[col].dropna()
            if len(s) < 10:
                continue

            mean, std = s.mean(), s.std()
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            lb_iqr = q1 - 1.5 * iqr
            ub_iqr = q3 + 1.5 * iqr

            z_scores = ((df[col] - mean) / std).abs()
            is_zscore = z_scores > 3
            is_iqr = (df[col] < lb_iqr) | (df[col] > ub_iqr)
            is_anomaly = is_zscore | is_iqr

            anomaly_rows = df[is_anomaly & df[col].notna()]
            count = len(anomaly_rows)

            if count > 0:
                examples = anomaly_rows[col].head(3).tolist()
                severity = "critical" if count > len(df) * 0.05 else "warning" if count > 2 else "info"
                summary["anomalies_by_column"][col] = {
                    "count": count,
                    "pct_of_data": round(count / len(df) * 100, 1),
                    "severity": severity,
                    "examples": [round(float(v), 2) for v in examples],
                    "normal_range": f"[{round(float(lb_iqr), 2)}, {round(float(ub_iqr), 2)}]",
                    "method": "Z-score (>3σ) + IQR (1.5× fence)",
                }
                anomalies.append({
                    "column": col,
                    "count": count,
                    "severity": severity,
                    "business_implication": (
                        f"'{col}' has {count} values outside normal range. "
                        f"Examples: {examples[:3]}. "
                        f"Investigate for data entry errors or genuine business events."
                    ),
                })

        summary["total_anomalous_columns"] = len(anomalies)
        summary["anomaly_details"] = anomalies
        summary["recommendation"] = (
            "No anomalies detected — data appears clean." if not anomalies
            else f"Found anomalies in {len(anomalies)} column(s). Review before drawing business conclusions."
        )

        return json.dumps(summary, default=str, indent=2)
    except Exception as exc:
        return f"detect_anomalies_advanced error: {exc}"


def _tool_benchmark_industry(metric_name: str, your_value: float, industry: str) -> str:
    """Compare a metric against industry standard benchmarks."""
    benchmarks: dict[str, dict[str, dict[str, float]]] = {
        "retail": {
            "gross_margin": {"p25": 28.0, "median": 38.0, "p75": 52.0, "best_in_class": 65.0},
            "revenue_growth": {"p25": 2.0, "median": 5.0, "p75": 12.0, "best_in_class": 25.0},
            "customer_retention": {"p25": 55.0, "median": 65.0, "p75": 78.0, "best_in_class": 90.0},
            "inventory_turnover": {"p25": 4.0, "median": 6.5, "p75": 10.0, "best_in_class": 15.0},
        },
        "finance": {
            "net_interest_margin": {"p25": 2.0, "median": 3.0, "p75": 4.2, "best_in_class": 5.5},
            "cost_income_ratio": {"p25": 70.0, "median": 58.0, "p75": 48.0, "best_in_class": 38.0},
            "return_on_equity": {"p25": 6.0, "median": 11.0, "p75": 16.0, "best_in_class": 22.0},
            "revenue_growth": {"p25": 2.0, "median": 5.5, "p75": 10.0, "best_in_class": 18.0},
        },
        "saas": {
            "gross_margin": {"p25": 65.0, "median": 75.0, "p75": 82.0, "best_in_class": 90.0},
            "net_revenue_retention": {"p25": 95.0, "median": 108.0, "p75": 120.0, "best_in_class": 140.0},
            "cac_payback_months": {"p25": 24.0, "median": 15.0, "p75": 10.0, "best_in_class": 6.0},
            "revenue_growth": {"p25": 15.0, "median": 30.0, "p75": 55.0, "best_in_class": 100.0},
        },
        "healthcare": {
            "operating_margin": {"p25": 2.0, "median": 5.0, "p75": 10.0, "best_in_class": 18.0},
            "revenue_growth": {"p25": 2.0, "median": 6.0, "p75": 12.0, "best_in_class": 20.0},
            "patient_satisfaction": {"p25": 72.0, "median": 82.0, "p75": 90.0, "best_in_class": 97.0},
        },
        "manufacturing": {
            "gross_margin": {"p25": 18.0, "median": 28.0, "p75": 38.0, "best_in_class": 52.0},
            "oee": {"p25": 55.0, "median": 70.0, "p75": 82.0, "best_in_class": 92.0},
            "inventory_turnover": {"p25": 5.0, "median": 8.0, "p75": 12.0, "best_in_class": 18.0},
            "revenue_growth": {"p25": 1.0, "median": 4.0, "p75": 8.0, "best_in_class": 15.0},
        },
    }
    industry_key = industry.lower().strip()
    metric_key = metric_name.lower().replace(" ", "_").replace("-", "_")

    industry_data = benchmarks.get(industry_key, benchmarks.get("retail", {}))
    metric_data = industry_data.get(metric_key)

    if not metric_data:
        available = list(industry_data.keys())
        return (
            f"Benchmark data not available for '{metric_name}' in '{industry}' industry. "
            f"Available metrics: {', '.join(available)}. "
            f"Your value: {your_value}. Consider researching industry-specific benchmarks."
        )

    p25, median, p75, bic = metric_data["p25"], metric_data["median"], metric_data["p75"], metric_data["best_in_class"]

    if your_value >= bic:
        percentile, status = "Top 5%", "BEST IN CLASS"
        gap_text = "You are outperforming best-in-class benchmarks."
    elif your_value >= p75:
        percentile, status = "Top 25%", "ABOVE AVERAGE"
        gap_text = f"Gap to best-in-class: {bic - your_value:.1f} points."
    elif your_value >= median:
        percentile, status = "Above median", "AVERAGE"
        gap_text = f"Gap to top quartile: {p75 - your_value:.1f} points. Gap to best-in-class: {bic - your_value:.1f} points."
    elif your_value >= p25:
        percentile, status = "Below median", "BELOW AVERAGE — ACTION NEEDED"
        gap_text = f"Gap to median: {median - your_value:.1f} points. This represents a significant improvement opportunity."
    else:
        percentile, status = "Bottom 25%", "CRITICAL — URGENT ACTION REQUIRED"
        gap_text = f"Gap to bottom quartile: {p25 - your_value:.1f} points. Gap to median: {median - your_value:.1f} points. Immediate intervention required."

    return json.dumps({
        "metric": metric_name,
        "your_value": your_value,
        "industry": industry,
        "status": status,
        "percentile_position": percentile,
        "benchmarks": {"p25": p25, "median": median, "p75": p75, "best_in_class": bic},
        "gap_analysis": gap_text,
        "recommendation": f"Target {p75} (top quartile) as 12-month goal; target {bic} (best-in-class) as 3-year goal.",
    }, indent=2)


def _tool_generate_action_plan(
    findings: list[str],
    priority_area: str,
    budget_context: str,
) -> str:
    """Generate a structured 30-60-90 day McKinsey-style action plan."""
    current_date = datetime.now().strftime("%B %d, %Y")
    plan = {
        "generated_at": current_date,
        "priority_area": priority_area,
        "budget_context": budget_context,
        "days_1_30": {
            "theme": "Immediate Impact — Stop the Bleeding",
            "actions": [
                f"Convene executive task force on {priority_area} — assign named owner with P&L accountability",
                "Conduct rapid data audit — identify top 3 root causes driving findings",
                f"Deploy quick-win interventions for highest-impact finding: {findings[0] if findings else 'primary finding'}",
                "Establish weekly KPI dashboard with automated alerts for key metrics",
                "Communicate findings to senior leadership with recommended resource reallocation",
            ],
        },
        "days_31_60": {
            "theme": "Structural Fixes — Build the Foundation",
            "actions": [
                f"Implement process redesign for {priority_area} based on root cause analysis",
                "Deploy corrective initiatives from findings 2 and 3" if len(findings) >= 3 else "Address secondary findings",
                "Launch A/B testing for top 2 recommended interventions",
                "Hire or reallocate talent to identified capability gaps",
                "Review vendor/partner contracts for cost optimization opportunities",
            ],
        },
        "days_61_90": {
            "theme": "Strategic Acceleration — Scale What Works",
            "actions": [
                "Scale winning interventions from Days 31-60 testing",
                f"Set 12-month targets for {priority_area} aligned to best-in-class benchmarks",
                "Establish ongoing monitoring program with monthly executive reviews",
                "Document lessons learned and build institutional playbook",
                "Model next 3-year scenario with DataMind forecasting",
            ],
        },
        "success_metrics": [
            "Week 4: Root cause identification complete, task force active",
            "Week 8: First measurable KPI improvement visible in dashboard",
            "Week 12: Full corrective plan deployed, forecast model running",
        ],
        "risk_of_inaction": (
            f"Without structured intervention in {priority_area}, "
            "the identified issues will compound quarterly. "
            "Based on findings, estimated annualized impact exceeds the cost of a full analyst team."
        ),
    }
    return json.dumps(plan, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
#  Agent
# ─────────────────────────────────────────────────────────────────────────────

class DataAnalystAgent:
    MAX_ITERATIONS = 12

    def __init__(self):
        self._charts: list[dict] = []
        self._report_sections: dict[str, str] = {}
        self._provider = _AGENT_PROVIDER

        if self._provider == "anthropic":
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
            logger.info("DataAnalystAgent using Anthropic Claude")
        else:
            import httpx
            self._http = httpx.Client(timeout=180.0)
            logger.info(f"DataAnalystAgent using Ollama model: {_OLLAMA_MODEL}")

    def _llm_call(self, system_prompt: str, messages: list, max_tokens: int = 800) -> tuple[str, int]:
        """Unified LLM call — returns (raw_text, tokens_used)."""
        if self._provider == "anthropic":
            anthropic_messages = [m for m in messages if m["role"] != "system"]
            response = self._anthropic_client.messages.create(
                model=_ANTHROPIC_MODEL,
                system=system_prompt,
                messages=anthropic_messages + [{"role": "assistant", "content": "{"}],
                max_tokens=max_tokens,
                temperature=0,
            )
            tokens = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0
            raw = "{" + (response.content[0].text if response.content else "}")
            return raw, tokens
        else:
            # Ollama
            ollama_messages = [{"role": "system", "content": system_prompt}] + [
                m for m in messages if m["role"] != "system"
            ]
            resp = self._http.post(
                f"{_OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": _OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": 8192},
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip()
            # Ensure we have valid JSON — strip any markdown fences
            if not raw.startswith("{"):
                start = raw.find("{")
                raw = raw[start:] if start != -1 else "{}"
            return raw, len(raw.split())

    def run(
        self,
        task: str,
        run_id: str,
        db: Session,
        user_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        db_connection_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> AgentResult:
        start = time.time()
        steps: list[AgentStep] = []
        total_tokens = 0
        self._charts = []
        self._report_sections = {}

        # ── Inject user memories into system prompt ──────────────────────────
        memory_block = ""
        if user_id:
            try:
                from services.agent_memory import AgentMemoryService
                memories_text = AgentMemoryService.get_user_memories(db, user_id, limit=5)
                if memories_text:
                    memory_block = memories_text
            except Exception as exc:
                logger.warning(f"Could not load memories for user {user_id}: {exc}")
        system_prompt = _build_system_prompt(memory_block=memory_block)

        # Build initial user message
        context_parts = [f"Task: {task}"]
        if dataset_id:
            context_parts.append(f"Dataset ID: {dataset_id}")
        if db_connection_id:
            context_parts.append(f"DB Connection ID: {db_connection_id}")
        if domain:
            context_parts.append(f"Analysis domain hint: {domain}")

        messages = [
            {"role": "user", "content": "\n".join(context_parts)},
        ]

        final_summary = "Analysis did not complete — max iterations reached."
        final_status = "failed"

        # Separate system prompt from conversation messages for Anthropic
        anthropic_system = system_prompt
        anthropic_messages = [m for m in messages if m["role"] != "system"]

        for i in range(1, self.MAX_ITERATIONS + 1):
            try:
                raw, tokens = self._llm_call(anthropic_system, anthropic_messages, max_tokens=800)
                total_tokens += tokens
                parsed = _parse_llm_response(raw)
            except json.JSONDecodeError as exc:
                logger.warning(f"Agent JSON parse error at step {i}: {exc} | raw={raw[:300]}")
                steps.append(AgentStep(
                    iteration=i,
                    thought="JSON parse error — skipping iteration",
                    action="error",
                    action_input={},
                    observation=f"Parse error: {exc}",
                    error=True,
                ))
                # Do NOT break — continue to next iteration so the agent can recover
                anthropic_messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response could not be parsed as JSON. "
                        "Please respond with ONLY a valid JSON object — no markdown fences, "
                        "no extra text, just the raw JSON starting with { and ending with }."
                    ),
                })
                continue
            except Exception as exc:
                logger.error(f"LLM call failed at step {i}: {exc}")
                exc_str = str(exc)
                if "WinError" in exc_str or "ConnectionRefusedError" in exc_str or "Errno 111" in exc_str or "Connection refused" in exc_str:
                    final_summary = (
                        "⚠️ AI Service Unavailable\n\n"
                        "The AI analysis engine could not connect to a language model. "
                        "To fix this, go to **Settings → AI Configuration** and either:\n\n"
                        "1. Add an **OpenAI API key** to use cloud-based AI (recommended).\n"
                        "2. Install and start **Ollama** locally, then enable \"Use Local Ollama\"."
                    )
                else:
                    final_summary = f"LLM error: {exc}"
                break

            thought = parsed.get("thought", "")
            action = parsed.get("action", "")
            action_input = parsed.get("action_input", {})

            # ── Execute tool with one retry on error ─────────────────────────
            observation, figs = self._execute_tool(action, action_input, dataset_id, db_connection_id, db)

            is_error = (
                observation.startswith("Tool error:")
                or observation.startswith("BLOCKED:")
                or observation.startswith("SQL error:")
                or observation.startswith("Error")
            )
            if is_error and action not in ("final_answer", "error"):
                logger.info(f"Tool {action} failed at step {i}, retrying once. Error: {observation[:200]}")
                retry_obs, retry_figs = self._execute_tool(action, action_input, dataset_id, db_connection_id, db)
                if not (
                    retry_obs.startswith("Tool error:")
                    or retry_obs.startswith("BLOCKED:")
                    or retry_obs.startswith("SQL error:")
                    or retry_obs.startswith("Error")
                ):
                    observation, figs = retry_obs, retry_figs
                    is_error = False

            step = AgentStep(
                iteration=i,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                figures=figs,
                error=is_error,
            )
            steps.append(step)

            anthropic_messages.append({"role": "assistant", "content": raw})
            anthropic_messages.append({"role": "user", "content": f"Observation: {observation[:3000]}"})

            if action == "final_answer":
                # New structured format: store full action_input as JSON so the
                # frontend can render executive_summary, key_findings, etc.
                # Legacy format: action_input contains just {"summary": "..."}
                if "executive_summary" in action_input:
                    final_summary = json.dumps(action_input)
                else:
                    final_summary = action_input.get("summary", observation)
                final_status = "completed"
                break

        # ── If max iterations hit without final_answer, synthesise from what we have ──
        if final_status == "failed" and steps and "LLM error" not in final_summary:
            try:
                # Collect any report sections and observations gathered so far
                gathered = ""
                if self._report_sections:
                    gathered = "\n\n".join(
                        f"## {sec}\n{content}" for sec, content in self._report_sections.items()
                    )
                else:
                    # Summarise step observations
                    obs_lines = [
                        f"Step {s.iteration} ({s.action}): {s.observation[:300]}"
                        for s in steps if not s.error and s.observation
                    ]
                    gathered = "\n".join(obs_lines[-10:])  # last 10 relevant observations

                forced_prompt = (
                    f"You have reached the iteration limit. Based on everything you have done so far, "
                    f"write a complete final_answer JSON now.\n\nFindings so far:\n{gathered[:3000]}\n\n"
                    "Respond with ONLY the JSON: "
                    '{"thought": "...", "action": "final_answer", "action_input": {"summary": "..."}}'
                )
                forced_msgs = anthropic_messages + [{"role": "user", "content": forced_prompt}]
                forced_raw, forced_tokens = self._llm_call(anthropic_system, forced_msgs, max_tokens=2000)
                total_tokens += forced_tokens
                forced_parsed = _parse_llm_response(forced_raw)
                if forced_parsed.get("action") == "final_answer":
                    final_summary = forced_parsed["action_input"].get("summary", gathered)
                    final_status = "completed"
                    logger.info(f"Forced final_answer after max iterations for run {run_id}")
            except Exception as exc:
                logger.warning(f"Could not force final_answer for run {run_id}: {exc}")
                # Fall back to report sections if available
                if self._report_sections:
                    final_summary = "\n\n".join(
                        f"## {sec}\n{content}" for sec, content in self._report_sections.items()
                    )
                    final_status = "completed"

        duration = round(time.time() - start, 2)

        # Build report from sections
        if self._report_sections and final_status == "completed":
            ordered_sections = "\n\n".join(
                f"## {sec}\n{content}"
                for sec, content in self._report_sections.items()
            )
            final_summary = ordered_sections or final_summary

        result = AgentResult(
            run_id=run_id,
            status=final_status,
            steps=steps,
            summary=final_summary,
            charts=self._charts,
            token_usage=total_tokens,
            duration_seconds=duration,
        )

        # ── Extract and save memories in background ──────────────────────────
        if user_id and final_status == "completed":
            import threading
            from models.database import SessionLocal
            from services.agent_memory import AgentMemoryService

            def _save_memories():
                mem_db = SessionLocal()
                try:
                    AgentMemoryService.extract_and_save_memories(
                        db=mem_db,
                        user_id=user_id,
                        run_id=run_id,
                        task=task,
                        steps=[
                            {
                                "iteration": s.iteration,
                                "action": s.action,
                                "observation": s.observation,
                            }
                            for s in steps
                        ],
                        summary=final_summary,
                    )
                finally:
                    mem_db.close()

            t = threading.Thread(target=_save_memories, daemon=True)
            t.start()

        return result

    # ------------------------------------------------------------------ #

    def _execute_tool(
        self,
        action: str,
        action_input: dict,
        dataset_id: Optional[str],
        db_connection_id: Optional[str],
        db: Session,
    ) -> tuple[str, list[str]]:
        """Dispatch tool call, return (observation, figures)."""
        try:
            if action == "get_dataset_info":
                did = action_input.get("dataset_id") or dataset_id
                return _tool_get_dataset_info(did, db), []

            elif action == "get_column_stats":
                did = action_input.get("dataset_id") or dataset_id
                cols = action_input.get("columns", [])
                return _tool_get_column_stats(did, cols, db), []

            elif action == "execute_python":
                code = action_input.get("code", "")
                return _tool_execute_python(code, dataset_id, db)

            elif action == "execute_sql":
                query = action_input.get("query", "SELECT 1")
                cid = action_input.get("connection_id") or db_connection_id
                return _tool_execute_sql(query, cid, db), []

            elif action == "compare_periods":
                return _tool_compare_periods(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    date_column=action_input.get("date_column", ""),
                    metric_column=action_input.get("metric_column", ""),
                    period1=str(action_input.get("period1", "")),
                    period2=str(action_input.get("period2", "")),
                    db=db,
                ), []

            elif action == "detect_anomalies":
                return _tool_detect_anomalies(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    columns=action_input.get("columns", []),
                    db=db,
                ), []

            elif action == "generate_executive_summary":
                return _tool_generate_executive_summary(
                    findings=action_input.get("findings", []),
                    recommendations=action_input.get("recommendations", []),
                    data_period=action_input.get("data_period", ""),
                ), []

            elif action == "search_domain_template":
                dom = action_input.get("domain", "")
                task_type = action_input.get("task_type", "")
                return _tool_search_domain_template(dom, task_type), []

            elif action == "search_web":
                return _tool_search_web(action_input.get("query", "")), []

            elif action == "auto_visualize":
                return _tool_auto_visualize(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    chart_type=action_input.get("chart_type", "bar"),
                    x_col=action_input.get("x_col", ""),
                    y_col=action_input.get("y_col"),
                    title=action_input.get("title", "Chart"),
                    db=db,
                )

            elif action == "save_chart":
                b64 = action_input.get("figure_base64", "")
                title = action_input.get("title", f"Chart {len(self._charts)+1}")
                if b64:
                    self._charts.append({"title": title, "base64": b64})
                return f"Chart '{title}' saved.", [b64] if b64 else []

            elif action == "write_report_section":
                section = action_input.get("section", "Section")
                content = action_input.get("content", "")
                self._report_sections[section] = content
                return f"Section '{section}' written ({len(content)} chars).", []

            elif action == "benchmark_industry":
                return _tool_benchmark_industry(
                    metric_name=action_input.get("metric_name", ""),
                    your_value=float(action_input.get("your_value", 0)),
                    industry=action_input.get("industry", "retail"),
                ), []

            elif action == "generate_action_plan":
                return _tool_generate_action_plan(
                    findings=action_input.get("findings", []),
                    priority_area=action_input.get("priority_area", "business performance"),
                    budget_context=action_input.get("budget_context", "unknown"),
                ), []

            elif action == "assess_data_quality":
                return _tool_assess_data_quality(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    db=db,
                ), []

            elif action == "clean_data":
                return _tool_clean_data(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    strategy=action_input.get("strategy", "auto"),
                    db=db,
                )

            elif action == "run_eda":
                return _tool_run_eda(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    db=db,
                )

            elif action == "detect_anomalies_advanced":
                return _tool_detect_anomalies_advanced(
                    dataset_id=action_input.get("dataset_id") or dataset_id or "",
                    columns=action_input.get("columns", []),
                    db=db,
                ), []

            elif action == "final_answer":
                return action_input.get("summary", "Done."), []

            else:
                return f"Unknown action: {action}", []

        except Exception as exc:
            logger.error(f"Tool execution error for {action}: {exc}")
            return f"Tool error: {exc}", []
