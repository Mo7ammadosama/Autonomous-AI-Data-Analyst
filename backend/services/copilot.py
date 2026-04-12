"""
Universal AI Copilot Orchestrator
Routes natural-language requests to the appropriate internal service.
Accessible from anywhere in the platform.
"""

import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def _detect_language(text: str) -> str:
    """Returns 'arabic' if >30% of chars are Arabic script, else 'english'."""
    if not text:
        return "english"
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return "arabic" if arabic_chars / len(text) > 0.3 else "english"


# Intent routing patterns
# Note: use \w* after prefix terms so word boundaries don't block prefix matching
_INTENT_PATTERNS = {
    "autonomous":    r"\b(fully\s+analyze|analyze\s+everything|run\s+everything|autonomous\s+analy\w*|complete\s+analy\w*|end.to.end|deep\s+dive\s+analy|generate\s+complete\s+report|complete\s+business\s+report)\b",
    "forecast":      r"\b(forecast\w*|predict\w*|projection|future|next\s+\d+\s+\w+|trend\s+ahead)\b",
    "anomaly":       r"\b(anomal\w*|unusual|strange|spike|drop\s+in|alert|weird|outlier\w*)\b",
    "dashboard":     r"\b(dashboard|kpi|create.{0,20}dashboard|build.{0,20}dashboard)\b",
    "correlation":   r"\b(correlat\w*|relationship|related\s+to|affect|impact|influence)\b",
    "distribution":  r"\b(distribut\w*|histogram|spread|frequency)\b",
    "top_n":         r"\b(top\s+\d+|best\s+\d+|highest|lowest|most|least|rank\w*|bottom\s+\d+)\b",
    "comparison":    r"\b(compare|vs\b|versus|difference\s+between|which\s+is\s+better|worse)\b",
    "trend":         r"\b(trend\w*|over\s+time|growth|decline|monthly|yearly|change\s+over)\b",
    "summary":       r"\b(summary|summarize|describe|profile|what\s+(are\s+)?the\s+columns|about\s+(the\s+)?data|explain\s+(the\s+)?dataset)\b",
    "recommendation":r"\b(recommend\w*|suggest\w*|advice|should\s+i|should\s+we|improve|action\s+item|strateg\w*)\b",
    "story":         r"\b(data\s+story|narrat\w*|explain\s+(the\s+)?finding|write\s+(a\s+)?report|tell\s+me\s+about)\b",
    "clean":         r"\b(clean\s+(the\s+)?data|fix\s+(the\s+)?data|missing\s+value|null\s+value|duplicate|data\s+quality)\b",
    "report":        r"\b(report|pdf|export|generate\s+(a\s+)?report)\b",
    "chat":          r".*",  # catch-all
}


def classify_intent(question: str) -> str:
    """Classify user intent from natural language question."""
    q = question.lower()
    for intent, pattern in _INTENT_PATTERNS.items():
        if re.search(pattern, q):
            return intent
    return "chat"


def _build_context_from_df(df) -> str:
    """Build a short textual context from a dataframe."""
    if df is None:
        return "No dataset loaded."
    cols = []
    for col in df.columns[:15]:
        cols.append(f"{col}({df[col].dtype})")
    return f"{len(df):,} rows × {len(df.columns)} cols: {', '.join(cols)}"


def handle_copilot_request(
    question: str,
    dataset_id: Optional[str],
    db,
    current_user: dict,
    llm_service,
) -> Dict[str, Any]:
    """
    Main copilot entry point.
    Routes to appropriate service based on detected intent.
    Returns a structured response with: answer, charts, insights, recommendations, type.
    """
    intent = classify_intent(question)
    logger.info(f"Copilot intent: {intent} | question: {question[:80]}")

    response: Dict[str, Any] = {
        "question": question,
        "intent": intent,
        "answer": "",
        "charts": [],
        "insights": [],
        "recommendations": [],
        "forecast": None,
        "anomalies": None,
        "type": intent,
    }

    # Pure conversational (no dataset needed)
    if intent == "chat" or not dataset_id:
        response["answer"] = _handle_conversational(question, llm_service)
        return response

    # Load dataset
    from models.database import Dataset
    from services.data_processor import load_dataset, compute_correlations, detect_outliers, profile_dataset

    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"]
    ).first()

    if not dataset:
        response["answer"] = "Dataset not found. Please select a valid dataset."
        return response

    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
    except Exception as e:
        response["answer"] = f"Could not load dataset: {str(e)}"
        return response

    context = _build_context_from_df(df)

    # Route to handler
    if intent == "autonomous":
        response.update(_handle_autonomous(dataset_id, current_user, db, llm_service))

    elif intent == "forecast":
        response.update(_handle_forecast(df, question, dataset_id, db))

    elif intent == "anomaly":
        response.update(_handle_anomaly(df))

    elif intent == "recommendation":
        response.update(_handle_recommendation(df, dataset, llm_service))

    elif intent == "story":
        response.update(_handle_story(df, dataset, llm_service))

    elif intent == "dashboard":
        response.update(_handle_dashboard(df, dataset, llm_service))

    elif intent == "report":
        response["answer"] = (
            "To generate a PDF report, visit the **Reports** section and click 'Generate Report'. "
            "I can also summarize findings here — just ask!"
        )

    else:
        # Route to existing AI agent for data analysis
        from services.ai_agent import AIDataAnalystAgent
        agent = AIDataAnalystAgent()
        agent_response = agent.analyze_question(question, df, dataset.name)
        response.update(agent_response)

    # Ensure we always have a readable answer
    if not response.get("answer"):
        response["answer"] = llm_service.generate_analysis_narrative(
            question, intent, response.get("insights", []), context
        )

    return response


def _handle_conversational(question: str, llm_service) -> str:
    """Handle general questions not tied to a dataset — supports Arabic."""
    lang = _detect_language(question)
    lang_instruction = (
        "أجب دائماً باللغة العربية. كن مباشراً وطبيعياً كأنك تتحدث مع صديق. لا تستخدم قوائم أو نقاط إلا إذا طُلب منك ذلك صراحةً."
        if lang == "arabic"
        else "Respond in the same language the user writes in. Be direct and conversational — avoid bullet lists and headers unless the user asks for structured output."
    )
    return llm_service.complete(
        system=(
            f"You are DataMind AI — an expert assistant for data analytics and general questions.\n"
            f"{lang_instruction}\n"
            "Answer questions directly and concisely. Do NOT describe your own architecture, training, or limitations "
            "unless explicitly asked. Do NOT start responses with 'As an AI...' or similar disclaimers. "
            "Just answer the question naturally and helpfully."
        ),
        user=question,
        max_tokens=800,
    )


def _handle_forecast(df, question: str, dataset_id: str, db) -> Dict[str, Any]:
    """Run forecasting and return results — only for time-series datasets."""
    from services.data_processor import detect_dataset_type
    from services.forecasting import run_forecast

    ds_type = detect_dataset_type(df)
    if ds_type["type"] == "CROSS_SECTIONAL":
        reason = ds_type.get("reason", "all records belong to the same time period")
        return {
            "answer": (
                "⚠️ **Forecasting Not Available**\n\n"
                f"This is a **cross-sectional dataset** — {reason}\n\n"
                "Forecasting requires data across **multiple time periods**. "
                "To forecast, please load a dataset with time-series data (e.g., monthly sales, daily revenue).\n\n"
                "For this dataset, consider asking about:\n"
                "- Distribution analysis\n"
                "- Ranking & top-N queries\n"
                "- Correlation analysis\n"
                "- Anomaly detection"
            )
        }

    result = run_forecast(df, periods=30)
    if "error" in result:
        return {"answer": f"Forecasting error: {result['error']}"}
    return {
        "answer": result.get("summary", "Forecast generated successfully."),
        "charts": [result["chart"]] if result.get("chart") else [],
        "forecast": result,
    }


def _handle_anomaly(df) -> Dict[str, Any]:
    """Run anomaly detection and return structured results."""
    from services.anomaly_detector import detect_anomalies
    anomalies = detect_anomalies(df)
    alerts = anomalies.get("summary_alerts", [])
    answer = (
        "\n".join(alerts) if alerts
        else "✅ No significant anomalies detected in this dataset."
    )
    return {"answer": answer, "anomalies": anomalies}


def _handle_recommendation(df, dataset, llm_service) -> Dict[str, Any]:
    """Generate business recommendations."""
    from services.data_processor import compute_correlations, detect_outliers, profile_dataset
    from services.recommendation import generate_recommendations

    profile = profile_dataset(df)
    correlations = compute_correlations(df)
    outliers = detect_outliers(df)
    recs = generate_recommendations(df, profile, correlations, outliers, llm_service)

    answer_parts = ["## 💡 Business Recommendations\n"]
    for i, r in enumerate(recs[:5], 1):
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.get("priority", "low"), "⚪")
        answer_parts.append(f"**{i}. {priority_emoji} {r['title']}**\n{r['description']}\n\n_Action: {r['action']}_")

    return {
        "answer": "\n\n".join(answer_parts),
        "recommendations": recs,
    }


def _handle_story(df, dataset, llm_service) -> Dict[str, Any]:
    """Generate data story narrative."""
    from services.data_processor import profile_dataset, compute_correlations, compute_descriptive_stats
    from services.anomaly_detector import detect_anomalies
    from services.storytelling import generate_full_story
    from services.ai_agent import AIDataAnalystAgent

    profile = profile_dataset(df)
    stats = compute_descriptive_stats(df)
    correlations = compute_correlations(df)
    anomalies = detect_anomalies(df)
    agent = AIDataAnalystAgent()
    insights = agent.generate_insights(df, dataset.name)

    story = generate_full_story(
        dataset_name=dataset.name,
        profile=profile,
        stats=stats,
        correlations=correlations,
        insights=insights,
        anomalies=anomalies,
        llm_service=llm_service,
    )
    charts = []
    from services.visualization import generate_auto_charts
    try:
        charts = generate_auto_charts(df, max_charts=3)
    except Exception:
        pass

    return {"answer": story, "charts": charts, "insights": insights}


def _handle_autonomous(dataset_id: str, current_user: dict, db, llm_service) -> Dict[str, Any]:
    """Trigger the autonomous analysis pipeline and return a summary."""
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models.database import engine as db_engine

    db_url = str(db_engine.url)
    owner_id = current_user["sub"]

    def _bg():
        _engine = create_engine(db_url, connect_args={"check_same_thread": False})
        _Session = sessionmaker(bind=_engine)
        _db = _Session()
        try:
            from services.autonomous_pipeline import run_autonomous_analysis
            run_autonomous_analysis(dataset_id, _db, owner_id, llm_service)
        finally:
            _db.close()

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()

    answer = (
        "🤖 **Autonomous Analysis Started!**\n\n"
        "I've launched a full 9-stage analysis pipeline:\n"
        "1. 📊 Data profiling\n"
        "2. 📈 Statistical analysis\n"
        "3. 🔗 Correlation mapping *(numeric indicators only)*\n"
        "4. 🚨 Anomaly & outlier detection\n"
        "5. 📉 Time-series forecasting *(skipped for cross-sectional data)*\n"
        "6. 💡 AI insight generation\n"
        "7. 📋 Business recommendations\n"
        "8. 📖 Data story narrative\n"
        "9. 🎛️ Auto dashboard creation\n\n"
        "Navigate to **Auto Analyst** in the sidebar to monitor progress and view the complete results."
    )
    return {"answer": answer, "type": "autonomous"}


def _handle_dashboard(df, dataset, llm_service) -> Dict[str, Any]:
    """Auto-generate a dashboard layout."""
    from services.ai_agent import AIDataAnalystAgent
    from services.visualization import generate_auto_charts

    agent = AIDataAnalystAgent()
    dashboard = agent.generate_dashboard(f"Create dashboard for {dataset.name}", df)
    charts = dashboard.get("charts", generate_auto_charts(df, max_charts=6))
    insights = agent.generate_insights(df, dataset.name)

    answer = (
        f"## 📊 Auto-Generated Dashboard: {dataset.name}\n\n"
        f"Generated {len(charts)} visualizations with key metrics and trends. "
        f"You can also visit the **Dashboards** section to save and customize this view."
    )

    return {"answer": answer, "charts": charts, "insights": insights}
