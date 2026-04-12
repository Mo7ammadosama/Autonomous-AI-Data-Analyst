"""
Autonomous AI Data Analyst Agent
Orchestrates analysis, code generation, and insights
"""

import pandas as pd
import numpy as np
import json
import logging
import traceback
import re
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from services.data_processor import (
    load_dataset, profile_dataset, compute_correlations,
    compute_descriptive_stats, detect_outliers, clean_dataset, sample_data_for_chart
)
from services.visualization import generate_auto_charts, generate_correlation_heatmap
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class SafeCodeExecutor:
    """Secure Python code executor with restricted globals"""

    FORBIDDEN_PATTERNS = [
        r'\bimport\s+os\b', r'\bimport\s+sys\b', r'\bimport\s+subprocess\b',
        r'\bopen\s*\(', r'\bexec\s*\(', r'\beval\s*\(', r'__import__',
        r'shutil', r'socket', r'urllib', r'requests', r'httpx',
    ]

    def execute(self, code: str, df: pd.DataFrame) -> Tuple[Any, str, Optional[str]]:
        """Execute code safely and return (result, output, error)"""
        # Check for forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                return None, "", f"Forbidden operation detected: {pattern}"

        import io
        import contextlib

        safe_globals = {
            "__builtins__": {
                "print": print, "len": len, "range": range, "enumerate": enumerate,
                "zip": zip, "map": map, "filter": filter, "list": list, "dict": dict,
                "tuple": tuple, "set": set, "str": str, "int": int, "float": float,
                "bool": bool, "round": round, "abs": abs, "min": min, "max": max,
                "sum": sum, "sorted": sorted, "reversed": reversed, "type": type,
                "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
            },
            "pd": pd, "np": np, "df": df.copy(),
            "json": json, "datetime": datetime,
        }

        output_buffer = io.StringIO()
        result = None

        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(code, safe_globals)
                result = safe_globals.get("result", None)
        except Exception as e:
            return None, output_buffer.getvalue(), str(e)

        return result, output_buffer.getvalue(), None


class AIDataAnalystAgent:
    """Main autonomous agent"""

    def __init__(self):
        self.executor = SafeCodeExecutor()
        self.llm = LLMService()

    # ── Varied response openers per intent ──────────────────────
    _OPENERS = {
        "summary":      ["Here's the full picture:", "Let me walk you through the data:", "Here's what the dataset looks like:", "Here's everything at a glance:"],
        "correlation":  ["Here's how the columns relate:", "Let me show you the connections:", "Here are the relationships I found:", "Here's the correlation breakdown:"],
        "distribution": ["Here's how the data is spread:", "Let me show you the distribution:", "Here's what the spread looks like:", "Here's the distribution:"],
        "trend":        ["Here's how things change over time:", "Let me show you the trend:", "Here's the trend analysis:", "Here's what I found about the trend:"],
        "outlier":      ["Here's what stands out:", "Found some interesting anomalies:", "Here are the unusual data points:", "Here's the outlier analysis:"],
        "comparison":   ["Here's how they compare:", "Let me break down the comparison:", "Here's the side-by-side view:", "Here's what the comparison shows:"],
        "top_n":        ["Here are the top performers:", "Here's your ranking:", "Here's the leaderboard:", "Here are the results:"],
        "generic":      ["Here's what I found:", "Let me dig into that:", "Here's my analysis:", "Good question — here's the breakdown:"],
    }

    def _pick_opener(self, intent: str) -> str:
        import random
        options = self._OPENERS.get(intent, self._OPENERS["generic"])
        return random.choice(options)

    def analyze_question(self, question: str, df: pd.DataFrame, dataset_name: str,
                         history: list = None) -> Dict[str, Any]:
        """Main entry point: analyze user question and return full response"""
        logger.info(f"Analyzing question: {question}")

        context = self._build_df_context(df)
        session_facts = self._extract_session_facts(history or [])
        intent = self._classify_intent(question, session_facts)

        response = {
            "question": question,
            "intent": intent,
            "answer": "",
            "charts": [],
            "code": None,
            "insights": [],
            "data_table": None,
        }

        try:
            if intent == "greeting":
                response.update(self._handle_greeting(df, dataset_name, question, session_facts))
            elif intent == "followup":
                response.update(self._handle_followup(df, question, session_facts))
            elif intent == "summary":
                response.update(self._handle_summary(df, dataset_name, session_facts))
            elif intent == "correlation":
                response.update(self._handle_correlation(df, session_facts))
            elif intent == "distribution":
                response.update(self._handle_distribution(df, question, session_facts))
            elif intent == "trend":
                response.update(self._handle_trend(df, question, session_facts))
            elif intent == "outlier":
                response.update(self._handle_outliers(df, session_facts))
            elif intent == "comparison":
                response.update(self._handle_comparison(df, question, session_facts))
            elif intent == "top_n":
                response.update(self._handle_top_n(df, question, session_facts))
            else:
                response.update(self._handle_generic(df, question, context, session_facts))

            if not response.get("answer"):
                num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                basic = f"Done! Here's a quick look:\n\n"
                if num_cols:
                    s = df[num_cols[0]].dropna()
                    basic += f"`{num_cols[0]}`: mean={s.mean():.2f}, range=[{s.min():.2f}, {s.max():.2f}]"
                response["answer"] = basic

        except Exception as e:
            logger.error(f"Agent error: {traceback.format_exc()}")
            response["answer"] = f"Hmm, I ran into an issue with that: *{str(e)}*. Try rephrasing — or ask for a summary first!"

        return response

    def _build_df_context(self, df: pd.DataFrame) -> str:
        cols = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            cols.append(f"{col} ({dtype})")
        return f"Dataset: {len(df)} rows x {len(df.columns)} columns. Columns: {', '.join(cols[:20])}"

    def _extract_session_facts(self, history: list) -> dict:
        """Scan conversation history to extract user name, last topic, last answer."""
        facts = {"user_name": None, "last_intent": None, "last_answer_preview": ""}
        name_prefixes = ("i am ", "i'm ", "my name is ", "call me ", "iam ")
        for msg in history:
            role = msg.get("role", "")
            content = (msg.get("content") or "").strip()
            if role == "user":
                low = content.lower()
                for p in name_prefixes:
                    if low.startswith(p):
                        candidate = content[len(p):].strip().split()[0].capitalize()
                        if len(candidate) > 1:
                            facts["user_name"] = candidate
                        break
            elif role == "assistant":
                facts["last_answer_preview"] = content[:200]
                # Try to detect last intent from answer structure
                low = content.lower()
                if "correlation" in low or "pearson" in low:
                    facts["last_intent"] = "correlation"
                elif "outlier" in low or "anomal" in low:
                    facts["last_intent"] = "outlier"
                elif "trend" in low or "over time" in low:
                    facts["last_intent"] = "trend"
                elif "top " in low or "leaderboard" in low or "ranking" in low:
                    facts["last_intent"] = "top_n"
                elif "distribution" in low or "histogram" in low or "spread" in low:
                    facts["last_intent"] = "distribution"
                elif "comparison" in low or "versus" in low:
                    facts["last_intent"] = "comparison"
                elif "rows" in low and "columns" in low:
                    facts["last_intent"] = "summary"
        return facts

    def _name_suffix(self, session_facts: dict) -> str:
        """Return ', Name' if name known, else empty string."""
        name = session_facts.get("user_name")
        return f", {name}" if name else ""

    def _classify_intent(self, question: str, session_facts: dict = None) -> str:
        q = question.lower().strip()
        session_facts = session_facts or {}

        # Short/exact greetings
        _exact_greetings = {"hi", "hello", "hey", "help", "how are you", "what can you do", "?",
                            "good morning", "good afternoon", "good evening", "thanks", "thank you",
                            "ok", "okay", "sure", "nice", "cool", "great", "awesome", "perfect",
                            "wow", "interesting", "got it", "i see", "understood"}
        if q in _exact_greetings or len(q) < 4:
            return "greeting"
        if any(q.startswith(p) for p in ("i am ", "i'm ", "my name is ", "call me ", "iam ")):
            return "greeting"

        # Follow-up / continuation
        _followup = ["tell me more", "more detail", "elaborate", "explain that", "explain more",
                     "why is that", "why?", "how so", "what do you mean", "can you clarify",
                     "go on", "continue", "and?", "so what", "what does that mean",
                     "can you expand", "dig deeper", "more info", "give me more"]
        if any(q == p or q.startswith(p) for p in _followup):
            return "followup"
        # Short "why" / "how" alone
        if q in ("why", "how", "what", "so", "and"):
            return "followup"

        if any(w in q for w in ["summary", "overview", "describe", "profile", "what columns", "what data", "tell me about"]):
            return "summary"
        if any(w in q for w in ["correlat", "relationship", "related to", "affect"]):
            return "correlation"
        if any(w in q for w in ["distribut", "histogram", "spread", "range"]):
            return "distribution"
        if any(w in q for w in ["trend", "over time", "change", "growth", "decline", "monthly", "yearly"]):
            return "trend"
        if any(w in q for w in ["outlier", "anomal", "unusual", "strange", "weird"]):
            return "outlier"
        if any(w in q for w in ["compare", "comparison", "versus", " vs ", "difference between"]):
            return "comparison"
        if any(w in q for w in ["top ", "best ", "highest", "lowest", "most", "least", "rank"]):
            return "top_n"
        return "generic"

    def _handle_summary(self, df: pd.DataFrame, name: str, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        profile = profile_dataset(df)
        stats = compute_descriptive_stats(df)
        charts = generate_auto_charts(df, max_charts=4)
        insights = self._generate_summary_insights(df, profile)
        suffix = self._name_suffix(session_facts)

        answer = f"{self._pick_opener('summary')}{suffix}\n\n"
        answer += f"**{name}** — 📊 **{profile['shape']['rows']:,} rows** × **{profile['shape']['columns']} columns**\n\n"

        if profile["missing_summary"]:
            answer += f"⚠️ Missing data in {len(profile['missing_summary'])} column(s)\n"
        if profile["duplicates"] > 0:
            answer += f"🔁 {profile['duplicates']} duplicate rows\n\n"

        answer += "**Columns:**\n"
        for col, info in list(profile["columns"].items())[:8]:
            answer += f"- **{col}**: {info['semantic_type']} | {info['unique_count']} unique"
            if info.get("mean") is not None:
                answer += f" | mean={info['mean']}"
            answer += "\n"

        answer += "\n*Want to dig into any specific column or pattern?*"
        return {"answer": answer, "charts": charts, "insights": insights}

    def _handle_correlation(self, df: pd.DataFrame, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        try:
            # Work only on numeric columns, drop fully-NaN columns
            numeric_df = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all")
            # Exclude rank/year/id columns that add no analytical value
            _SKIP = {"year", "yr", "id", "rank", "no", "number", "index", "sno"}
            clean_cols = [c for c in numeric_df.columns if c.lower().strip() not in _SKIP
                          and not c.lower().startswith("rank")]
            if len(clean_cols) >= 2:
                numeric_df = numeric_df[clean_cols]

            if numeric_df.shape[1] < 2:
                return {"answer": "Need at least 2 numeric columns for correlation analysis."}

            corr_data = compute_correlations(numeric_df)
            if not corr_data:
                return {"answer": "Need at least 2 numeric columns for correlation analysis."}

            chart = generate_correlation_heatmap(numeric_df)
            charts = [chart] if chart else []
            pairs = corr_data.get("strong_pairs", [])

            insights = []
            for pair in pairs[:5]:
                direction = "positively" if pair["correlation"] > 0 else "negatively"
                insights.append({
                    "title": f"Strong Correlation: {pair['col1']} ↔ {pair['col2']}",
                    "content": f"{pair['col1']} and {pair['col2']} are {direction} correlated (r={pair['correlation']:.2f})",
                    "type": "correlation",
                })

            opener = self._pick_opener("correlation") + self._name_suffix(session_facts)
            if pairs:
                answer = f"{opener}\n\nFound **{len(pairs)} strong correlations** (|r| ≥ 0.7):\n\n"
                for p in pairs[:8]:
                    arrow = "↑" if p["correlation"] > 0 else "↓"
                    strength = "very strong" if abs(p["correlation"]) >= 0.9 else "strong"
                    answer += f"- **{p['col1']}** {arrow} **{p['col2']}**: r = {p['correlation']:.3f} ({strength})\n"
                answer += "\n*Want me to explain what any of these mean in practice?*"
            else:
                cols = corr_data.get("columns", [])
                answer = f"{opener}\n\nNo strong correlations (|r| ≥ 0.7) found among {len(cols)} numeric columns — the variables appear to be relatively independent of each other.\n"
                answer += "\n*Try asking for outliers or a distribution breakdown instead.*"

            return {"answer": answer, "charts": charts, "insights": insights}

        except Exception as e:
            logger.error(f"Correlation analysis error: {e}")
            return {
                "answer": (
                    "⚠️ **Correlation Analysis Failed**\n\n"
                    f"Could not compute correlations: {str(e)}\n\n"
                    "Please ensure the dataset has at least 2 numeric columns with valid (non-null) values."
                ),
                "charts": [],
                "insights": [],
            }

    def _handle_distribution(self, df: pd.DataFrame, question: str, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return {"answer": "No numeric columns for distribution analysis."}

        # Find mentioned column
        target_col = None
        for col in numeric_cols:
            if col.lower() in question.lower():
                target_col = col
                break

        cols_to_plot = [target_col] if target_col else numeric_cols[:3]
        charts = []
        for col in cols_to_plot:
            sample = sample_data_for_chart(df)
            charts.append({
                "type": "histogram",
                "title": f"Distribution of {col}",
                "data": {"x": sample[col].dropna().tolist(), "type": "histogram", "name": col},
                "layout": {"title": f"Distribution of {col}", "xaxis_title": col, "yaxis_title": "Frequency"},
            })

        opener = self._pick_opener("distribution") + self._name_suffix(session_facts)
        answer = f"{opener}\n\n"
        for col in cols_to_plot:
            s = df[col].dropna()
            skew = float(s.skew())
            answer += f"**{col}**: mean={s.mean():.2f}, std={s.std():.2f}, "
            answer += f"skew={'right-skewed 📈' if skew > 0.5 else 'left-skewed 📉' if skew < -0.5 else 'roughly normal ✅'}\n"
        answer += "\n*Want me to check for outliers in any of these?*"
        return {"answer": answer, "charts": charts}

    def _handle_trend(self, df: pd.DataFrame, question: str, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        from services.data_processor import detect_dataset_type
        ds_type = detect_dataset_type(df)

        # Cross-sectional dataset: redirect to distribution + ranking analysis
        if ds_type["type"] == "CROSS_SECTIONAL":
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            # Skip year/id columns
            _SKIP = {"year", "yr", "id", "rank", "no", "number", "index"}
            meaningful = [c for c in numeric_cols if c.lower().strip() not in _SKIP]
            cols_to_plot = meaningful[:3] if meaningful else numeric_cols[:3]

            charts = []
            for col in cols_to_plot:
                sample = sample_data_for_chart(df)
                charts.append({
                    "type": "histogram",
                    "title": f"Distribution of {col}",
                    "data": [{"x": sample[col].dropna().tolist(), "type": "histogram", "name": col,
                               "marker": {"color": "#6366f1"}}],
                    "layout": {"title": f"Distribution: {col}", "xaxis": {"title": col}, "yaxis": {"title": "Count"},
                               "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
                               "font": {"color": "#94a3b8"}},
                })

            reason = ds_type.get("reason", "all records belong to the same time period")
            answer = (
                "⚠️ **Trend Analysis Not Applicable**\n\n"
                f"This is a **cross-sectional dataset** — {reason}\n\n"
                "Trend analysis requires data across multiple time periods. "
                "Showing **distribution analysis** of key metrics instead:\n\n"
            )
            for col in cols_to_plot:
                s = df[col].dropna()
                if len(s) == 0:
                    continue
                answer += f"**{col}**: mean={s.mean():.2f}, min={s.min():.2f}, max={s.max():.2f}\n"

            return {"answer": answer, "charts": charts}

        # Time-series dataset: normal trend analysis
        date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
        if not date_cols:
            for col in df.columns:
                try:
                    df[col] = pd.to_datetime(df[col])
                    date_cols.append(col)
                    break
                except Exception:
                    pass

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not date_cols or not numeric_cols:
            return {"answer": "Need a date column and numeric columns for trend analysis."}

        date_col = date_cols[0]
        value_col = numeric_cols[0]
        df_sorted = df.sort_values(date_col)

        charts = [{
            "type": "line",
            "title": f"{value_col} Over Time",
            "data": [{"x": df_sorted[date_col].astype(str).tolist()[:500],
                      "y": df_sorted[value_col].tolist()[:500],
                      "type": "scatter", "mode": "lines+markers", "name": value_col,
                      "line": {"color": "#6366f1", "width": 2}}],
            "layout": {"title": f"{value_col} Over Time",
                       "xaxis": {"title": date_col}, "yaxis": {"title": value_col},
                       "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
                       "font": {"color": "#94a3b8"}},
        }]

        first_val = df_sorted[value_col].iloc[0]
        last_val = df_sorted[value_col].iloc[-1]
        change_pct = (last_val - first_val) / abs(first_val) * 100 if first_val != 0 else 0
        direction = "increased" if change_pct > 0 else "decreased"

        opener = self._pick_opener("trend") + self._name_suffix(session_facts)
        answer = f"{opener}\n\n"
        answer += f"**{value_col}** has **{direction}** by {abs(change_pct):.1f}% over the period.\n"
        answer += f"- Start: {first_val:.2f} → End: {last_val:.2f}\n"
        answer += f"- Peak: {df_sorted[value_col].max():.2f} | Trough: {df_sorted[value_col].min():.2f}\n"
        answer += "\n*Curious about what drove this change? Ask me to check for correlations or outliers.*"
        return {"answer": answer, "charts": charts}

    def _handle_outliers(self, df: pd.DataFrame, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        outliers = detect_outliers(df)
        if not outliers:
            return {"answer": f"Good news{self._name_suffix(session_facts)} — no significant outliers detected in any numeric column. The data looks clean! 🎉"}

        charts = []
        for col, info in list(outliers.items())[:3]:
            sample = sample_data_for_chart(df)
            charts.append({
                "type": "box",
                "title": f"Outlier Analysis: {col}",
                "data": {"y": sample[col].dropna().tolist(), "type": "box", "name": col},
                "layout": {"title": f"Box Plot: {col}"},
            })

        opener = self._pick_opener("outlier") + self._name_suffix(session_facts)
        answer = f"{opener}\n\nFound anomalies in **{len(outliers)} column(s)**:\n\n"
        for col, info in outliers.items():
            answer += f"- **{col}**: {info['count']} outliers ({info['pct']:.1f}% of data) — normal range: [{info['lower_bound']:.2f}, {info['upper_bound']:.2f}]\n"
        answer += "\n*These could be data entry errors or genuinely extreme values. Want a deeper look at any of them?*"

        insights = [{"title": f"Outliers in {col}", "content": f"{info['count']} outliers ({info['pct']:.1f}%)", "type": "warning"}
                    for col, info in outliers.items()]

        return {"answer": answer, "charts": charts, "insights": insights}

    def _handle_comparison(self, df: pd.DataFrame, question: str, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        if not cat_cols or not num_cols:
            return {"answer": "Need both categorical and numeric columns for comparison."}

        cat_col = cat_cols[0]
        num_col = num_cols[0]

        grouped = df.groupby(cat_col)[num_col].mean().sort_values(ascending=False).head(15)
        charts = [{
            "type": "bar",
            "title": f"{num_col} by {cat_col}",
            "data": {"x": grouped.index.tolist(), "y": grouped.values.tolist(), "type": "bar", "name": num_col},
            "layout": {"title": f"Average {num_col} by {cat_col}", "xaxis_title": cat_col, "yaxis_title": f"Avg {num_col}"},
        }]

        opener = self._pick_opener("comparison") + self._name_suffix(session_facts)
        top = grouped.index[0]
        bottom = grouped.index[-1]
        answer = f"{opener}\n\n**{num_col}** grouped by **{cat_col}**:\n\n"
        answer += f"- 🥇 Highest: **{top}** ({grouped[top]:.2f})\n"
        answer += f"- 🔻 Lowest: **{bottom}** ({grouped[bottom]:.2f})\n"
        answer += f"- 📊 Spread: {grouped.max() - grouped.min():.2f}\n"
        answer += "\n*Want me to rank more categories or compare a different metric?*"
        return {"answer": answer, "charts": charts}

    def _handle_top_n(self, df: pd.DataFrame, question: str, session_facts: dict = None) -> Dict:
        session_facts = session_facts or {}
        # Extract N from question
        n = 10
        match = re.search(r'\b(\d+)\b', question)
        if match:
            n = min(int(match.group(1)), 50)

        # Skip non-meaningful numeric columns (year, rank, id, index)
        _SKIP_NUMERIC = {"year", "yr", "id", "rank", "no", "number", "index", "rank_", "sno"}
        all_num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        meaningful_num = [c for c in all_num_cols if c.lower().strip() not in _SKIP_NUMERIC
                          and not c.lower().startswith("rank")]
        num_cols = meaningful_num if meaningful_num else all_num_cols
        cat_cols = df.select_dtypes(include=["object"]).columns.tolist()

        if not num_cols:
            return {"answer": "No numeric columns to rank."}

        # Pick the most variance-rich numeric column if question doesn't name one explicitly
        num_col = num_cols[0]
        for col in num_cols:
            if col.lower() in question.lower():
                num_col = col
                break

        ascending = any(w in question.lower() for w in ["lowest", "least", "bottom", "worst"])
        top_n = df.nlargest(n, num_col) if not ascending else df.nsmallest(n, num_col)

        # Choose the best label column (first non-numeric, non-id col)
        cat_col = cat_cols[0] if cat_cols else None
        label = cat_col if cat_col else "Record"

        charts = []
        if cat_col:
            direction_label = "Bottom" if ascending else "Top"
            charts.append({
                "type": "bar",
                "title": f"{direction_label} {n} {label} by {num_col}",
                "data": [{
                    "x": top_n[cat_col].astype(str).tolist(),
                    "y": [round(float(v), 2) for v in top_n[num_col].tolist()],
                    "type": "bar",
                    "marker": {"color": "rgba(99, 102, 241, 0.8)"},
                }],
                "layout": {
                    "title": f"{direction_label} {n} {label} by {num_col}",
                    "xaxis": {"title": label},
                    "yaxis": {"title": num_col},
                    "paper_bgcolor": "rgba(0,0,0,0)",
                    "plot_bgcolor": "rgba(0,0,0,0)",
                    "font": {"color": "#94a3b8"},
                },
            })

        opener = self._pick_opener("top_n") + self._name_suffix(session_facts)
        direction_label = "Bottom" if ascending else "Top"
        answer = f"{opener}\n\n**{direction_label} {n} {label} by {num_col}**\n\n"
        for i, (_, row) in enumerate(top_n.head(min(n, 10)).iterrows(), 1):
            cat_val = str(row[cat_col]) if cat_col else f"Record {i}"
            answer += f"{i}. **{cat_val}**: {float(row[num_col]):.2f}\n"
        answer += "\n*Want me to dig deeper into any of these entries?*"

        data_records = top_n.head(n).to_dict("records")
        for rec in data_records:
            for k, v in rec.items():
                if isinstance(v, (np.int64, np.float64)):
                    rec[k] = float(v)

        return {"answer": answer, "charts": charts, "data_table": data_records}

    def _handle_greeting(self, df: pd.DataFrame, dataset_name: str,
                         question: str = "", session_facts: dict = None) -> Dict:
        """Handle conversational greetings naturally, with memory of user's name."""
        import random
        session_facts = session_facts or {}
        q = question.lower().strip()
        known_name = session_facts.get("user_name")

        # Extract name if user is introducing themselves NOW
        new_name = None
        for prefix in ("i am ", "i'm ", "my name is ", "call me ", "iam "):
            if q.startswith(prefix):
                candidate = question[len(prefix):].strip().split()[0].capitalize()
                if len(candidate) > 1:
                    new_name = candidate
                break
        name = new_name or known_name

        if new_name:
            greetings = [
                f"Nice to meet you, **{new_name}**! I'm your AI data analyst.",
                f"Hey **{new_name}**! Great to have you here.",
                f"Hello **{new_name}**! Good to meet you.",
            ]
            answer = (
                f"{random.choice(greetings)}\n\n"
                f"Your dataset **\"{dataset_name}\"** is loaded — **{len(df):,} rows × {len(df.columns)} columns**. "
                f"What would you like to explore first?"
            )
            return {"answer": answer, "charts": [], "insights": []}

        # Thanks / positive acknowledgement
        if any(w in q for w in ("thanks", "thank you", "great", "cool", "nice", "awesome", "perfect", "wow", "interesting")):
            responses = [
                f"Happy to help{', ' + name if name else ''}! What else would you like to know?",
                f"Anytime{', ' + name if name else ''}! Any other questions about the data?",
                f"Glad that was useful! Want to explore something else?",
            ]
            return {"answer": random.choice(responses), "charts": [], "insights": []}

        # Understood / ok / got it
        if q in ("ok", "okay", "got it", "i see", "understood", "sure"):
            responses = [
                "Got it! What would you like to look at next?",
                "Sure thing! What else can I help you with?",
                "Alright! Just ask whenever you're ready.",
            ]
            return {"answer": random.choice(responses), "charts": [], "insights": []}

        # How are you
        if "how are you" in q:
            responses = [
                f"Doing great{', ' + name if name else ''}! Ready to analyze **\"{dataset_name}\"**. What would you like to explore?",
                f"All good{', ' + name if name else ''}! What are we looking into today?",
            ]
            return {"answer": random.choice(responses), "charts": [], "insights": []}

        # Generic hi/hello/help — first-time style, show capabilities
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        hi_variants = ["Hey", "Hi there", "Hello", "Hey there"]
        answer = f"{random.choice(hi_variants)}{', ' + name if name else ''}! I'm your AI data analyst.\n\n"
        answer += f"**\"{dataset_name}\"** is loaded — **{len(df):,} rows × {len(df.columns)} columns**. Here's what I can do:\n\n"
        answer += "- 📊 **Summary** — *'Give me an overview'*\n"
        answer += "- 🔗 **Correlations** — *'What columns are correlated?'*\n"
        answer += "- 📈 **Trends** — *'Show me trends over time'*\n"
        answer += "- 🔍 **Outliers** — *'Any anomalies?'*\n"
        answer += "- 🏆 **Top N** — *'Top 10 by sales'*\n"
        answer += "- ⚖️ **Compare** — *'Compare revenue by category'*\n\n"
        if num_cols:
            answer += f"**Numeric columns**: {', '.join(f'`{c}`' for c in num_cols[:5])}\n"
        if cat_cols:
            answer += f"**Categorical columns**: {', '.join(f'`{c}`' for c in cat_cols[:5])}\n"
        answer += "\nWhat would you like to explore?"
        return {"answer": answer, "charts": [], "insights": []}

    def _handle_followup(self, df: pd.DataFrame, question: str, session_facts: dict) -> Dict:
        """Handle follow-up questions by routing to the last intent's handler with more depth."""
        last_intent = session_facts.get("last_intent")
        last_preview = session_facts.get("last_answer_preview", "")
        name = session_facts.get("user_name")
        name_part = f", {name}" if name else ""

        intro_variants = [
            f"Sure{name_part}! Here's a deeper look:",
            f"Good question{name_part}! Let me expand on that:",
            f"Of course{name_part}! Here's more detail:",
            f"Happy to dig deeper{name_part}!",
        ]
        import random
        intro = random.choice(intro_variants)

        # Pass empty session_facts to sub-handlers to suppress their name suffix
        # (intro already handles the personalization above)
        bare = {}

        if last_intent == "correlation":
            result = self._handle_correlation(df, bare)
        elif last_intent == "outlier":
            result = self._handle_outliers(df, bare)
        elif last_intent == "trend":
            result = self._handle_trend(df, question, bare)
        elif last_intent == "distribution":
            result = self._handle_distribution(df, question, bare)
        elif last_intent == "top_n":
            result = self._handle_top_n(df, question, bare)
        elif last_intent == "comparison":
            result = self._handle_comparison(df, question, bare)
        else:
            result = self._handle_summary(df, "the dataset", bare)

        # Strip the sub-handler's opener line (first line) and replace with our intro
        lines = result["answer"].split("\n")
        # First line is usually the opener ("Here's the full picture:\n\n"), skip it + blank lines after
        skip = 0
        for i, line in enumerate(lines):
            if line.strip():
                skip = i + 1
                break
        body = "\n".join(lines[skip:]).lstrip("\n")
        result["answer"] = f"{intro}\n\n{body}"
        return result

    def _handle_generic(self, df: pd.DataFrame, question: str, context: str,
                        session_facts: dict = None) -> Dict:
        """Generic handler: tries LLM code generation, falls back to data-driven stats."""
        session_facts = session_facts or {}
        code = self.llm.generate_analysis_code(question, context)
        charts = generate_auto_charts(df, max_charts=2)
        insights: list = []
        output = ""

        if code:
            _, output, error = self.executor.execute(code, df)
            if error:
                logger.warning(f"Code execution error: {error}")

        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        opener = self._pick_opener("generic") + self._name_suffix(session_facts)
        answer = f"{opener}\n\n"

        if num_cols:
            answer += "**Numeric summary:**\n"
            for col in num_cols[:4]:
                s = df[col].dropna()
                if len(s):
                    answer += (
                        f"- `{col}`: min={s.min():.2f}, max={s.max():.2f}, "
                        f"mean={s.mean():.2f}, std={s.std():.2f}\n"
                    )

        if cat_cols:
            answer += "\n**Categorical columns:**\n"
            for col in cat_cols[:3]:
                top = df[col].value_counts().index[0] if df[col].notna().any() else "N/A"
                nunique = df[col].nunique()
                answer += f"- `{col}`: {nunique} unique values, most common: **{top}**\n"

        if output:
            answer += f"\n**Computed result:**\n```\n{output[:400]}\n```"

        if not num_cols and not cat_cols:
            answer = (
                "I couldn't find relevant columns for that question. "
                "Try *'give me a summary'*, *'show correlations'*, or *'top 10 by [column]'*."
            )
        else:
            answer += "\n*Want me to focus on a specific column or go deeper on any of these?*"

        return {"answer": answer, "charts": charts, "code": code, "insights": insights}

    def _generate_summary_insights(self, df: pd.DataFrame, profile: Dict) -> List[Dict]:
        insights = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        for col in numeric_cols[:3]:
            s = df[col].dropna()
            if len(s) == 0:
                continue
            skew = float(s.skew())
            if abs(skew) > 1:
                insights.append({
                    "title": f"Skewed Distribution: {col}",
                    "content": f"'{col}' shows {'right' if skew > 0 else 'left'}-skewed distribution (skew={skew:.2f}), suggesting outliers.",
                    "type": "distribution",
                })

        missing_cols = [(c, i["pct"]) for c, i in profile.get("missing_summary", {}).items() if i["pct"] > 10]
        for col, pct in missing_cols[:3]:
            insights.append({
                "title": f"High Missing Rate: {col}",
                "content": f"Column '{col}' has {pct:.1f}% missing values which may affect analysis accuracy.",
                "type": "warning",
            })

        return insights

    def generate_dashboard(self, command: str, df: pd.DataFrame) -> Dict[str, Any]:
        """Auto-generate dashboard from natural language command"""
        charts = generate_auto_charts(df, max_charts=6)
        profile = profile_dataset(df)

        layout = {
            "title": command.replace("create", "").replace("dashboard", "").strip().title() or "Auto Dashboard",
            "charts": charts,
            "summary_stats": {
                col: {"mean": info.get("mean"), "type": info.get("semantic_type")}
                for col, info in list(profile["columns"].items())[:6]
                if info.get("mean") is not None
            },
        }
        return layout

    def generate_insights(self, df: pd.DataFrame, dataset_name: str) -> List[Dict]:
        """Generate automated business insights"""
        insights = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object"]).columns.tolist()

        # Descriptive insights
        for col in numeric_cols[:3]:
            s = df[col].dropna()
            if len(s) == 0:
                continue
            pct_75 = float(s.quantile(0.75))
            pct_25 = float(s.quantile(0.25))
            mean = float(s.mean())
            insights.append({
                "title": f"{col} Performance",
                "content": f"Average {col} is {mean:.2f}. Top 25% achieve {pct_75:.2f}+, while bottom 25% are below {pct_25:.2f}.",
                "type": "metric",
                "severity": "info",
                "metric_value": f"{mean:.2f}",
            })

        # Categorical insights — use neutral language (higher score ≠ better)
        for cat_col in cat_cols[:2]:
            if not numeric_cols:
                break
            # Skip year/id columns for ranking
            _SKIP = {"year", "yr", "id", "rank", "no", "number", "index"}
            meaningful = [c for c in numeric_cols if c.lower().strip() not in _SKIP]
            num_col = meaningful[0] if meaningful else numeric_cols[0]
            try:
                grouped = df.groupby(cat_col)[num_col].mean()
                highest = grouped.idxmax()
                lowest = grouped.idxmin()
                diff_pct = (grouped.max() - grouped.min()) / abs(grouped.min()) * 100 if grouped.min() != 0 else 0
                insights.append({
                    "title": f"Highest {num_col}: {highest}",
                    "content": (
                        f"'{highest}' has the highest average {num_col} ({grouped.max():.2f}), "
                        f"compared to '{lowest}' with the lowest ({grouped.min():.2f}). "
                        f"Spread: {diff_pct:.1f}%."
                    ),
                    "type": "comparison",
                    "severity": "info",
                    "metric_value": f"{grouped.max():.2f}",
                    "metric_change": diff_pct,
                })
            except Exception:
                pass

        # Anomaly insight
        outliers = detect_outliers(df)
        if outliers:
            worst_col = max(outliers, key=lambda c: outliers[c]["count"])
            insights.append({
                "title": f"Anomaly Alert: {worst_col}",
                "content": f"Detected {outliers[worst_col]['count']} anomalous values in '{worst_col}' ({outliers[worst_col]['pct']:.1f}% of data). Review for data quality.",
                "type": "anomaly",
                "severity": "warning",
            })

        return insights[:8]
