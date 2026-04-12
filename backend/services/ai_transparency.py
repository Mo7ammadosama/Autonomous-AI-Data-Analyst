"""
AI Transparency Service — Databricks Genie + Qlik AutoML style.

Makes every AI answer inspectable:
- Which tables / chunks were retrieved?
- What SQL was generated?
- How confident is the answer?
- Which features drove the prediction? (SHAP values)

All functions are lightweight wrappers — they add a `thinking_trace`
dict to existing service responses without changing the core logic.
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  ThinkingTrace — records how AI arrived at its answer
# ═══════════════════════════════════════════════════════════════

@dataclass
class ThinkingTrace:
    """Immutable audit trail of AI reasoning steps."""
    # Retrieval
    chunks_retrieved: List[Dict[str, Any]] = field(default_factory=list)    # [{text, score}]
    tables_used: List[str] = field(default_factory=list)
    columns_used: List[str] = field(default_factory=list)

    # Generation
    sql_generated: Optional[str] = None
    prompt_summary: Optional[str] = None                # trimmed prompt (no PII)
    model_used: Optional[str] = None

    # Confidence & quality
    confidence_score: float = 0.0                       # 0.0 – 1.0
    confidence_reason: str = ""                         # human-readable explanation
    grounding_sources: List[str] = field(default_factory=list)  # ["rag_chunk", "semantic_layer", "schema"]

    # Timing
    retrieval_ms: int = 0
    generation_ms: int = 0
    total_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@contextmanager
def timed_step(trace: ThinkingTrace, step: str):
    """Context manager to time a step and record it."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if step == "retrieval":
            trace.retrieval_ms = elapsed_ms
        elif step == "generation":
            trace.generation_ms = elapsed_ms
        trace.total_ms += elapsed_ms


# ═══════════════════════════════════════════════════════════════
#  Confidence Scorer
# ═══════════════════════════════════════════════════════════════

def score_confidence(
    sql_generated: Optional[str] = None,
    chunks_retrieved: Optional[List[Dict]] = None,
    chunk_scores: Optional[List[float]] = None,
    semantic_layer_used: bool = False,
    answer_length: int = 0,
) -> tuple[float, str]:
    """
    Heuristic confidence score (0.0 – 1.0) for an AI-generated answer.
    Returns (score, reason_string).
    """
    score = 0.5
    reasons = []

    # SQL quality signals
    if sql_generated:
        if "SELECT" in sql_generated.upper():
            score += 0.1
            reasons.append("valid SQL generated")
        if "JOIN" in sql_generated.upper():
            score += 0.05
            reasons.append("multi-table join")
        if any(kw in sql_generated.upper() for kw in ("INSERT", "UPDATE", "DELETE", "DROP")):
            score -= 0.3
            reasons.append("⚠️ unsafe SQL detected")

    # RAG retrieval quality
    if chunk_scores:
        avg_score = sum(chunk_scores) / len(chunk_scores)
        if avg_score > 0.7:
            score += 0.2
            reasons.append(f"high relevance chunks (avg {avg_score:.2f})")
        elif avg_score > 0.4:
            score += 0.1
            reasons.append(f"moderate relevance chunks (avg {avg_score:.2f})")
        else:
            score -= 0.1
            reasons.append(f"low relevance chunks (avg {avg_score:.2f})")
    elif not chunks_retrieved:
        score -= 0.1
        reasons.append("no context retrieved")

    # Semantic layer usage
    if semantic_layer_used:
        score += 0.15
        reasons.append("governed metric definition used")

    # Answer completeness
    if answer_length > 100:
        score += 0.05
        reasons.append("detailed answer")

    score = max(0.0, min(1.0, score))
    reason = "; ".join(reasons) if reasons else "standard generation"
    return round(score, 3), reason


# ═══════════════════════════════════════════════════════════════
#  SHAP-style Feature Importance (for AutoML)
# ═══════════════════════════════════════════════════════════════

def compute_feature_importance_explanation(
    model,
    X_sample,
    feature_names: List[str],
    task_type: str = "classification",
) -> List[Dict[str, Any]]:
    """
    Compute SHAP values if available, fall back to permutation importance.
    Returns sorted list of {feature, importance, direction, explanation}.
    """
    try:
        import shap
        import numpy as np

        explainer = shap.Explainer(model, X_sample)
        shap_values = explainer(X_sample)

        # Mean absolute SHAP across samples
        if hasattr(shap_values, "values"):
            vals = shap_values.values
            if vals.ndim == 3:
                vals = vals[:, :, 1]  # binary classification: class 1
            mean_abs = np.abs(vals).mean(axis=0)
        else:
            mean_abs = np.abs(shap_values).mean(axis=0)

        total = mean_abs.sum() or 1
        results = []
        for i, feat in enumerate(feature_names):
            importance = float(mean_abs[i] / total)
            mean_shap = float(vals[:, i].mean()) if vals.ndim == 2 else 0.0
            direction = "positive" if mean_shap > 0 else "negative"
            results.append({
                "feature": feat,
                "importance": round(importance, 4),
                "direction": direction,
                "explanation": (
                    f"{feat} {'increases' if direction == 'positive' else 'decreases'} "
                    f"the prediction by ~{importance * 100:.1f}%"
                ),
                "method": "shap",
            })
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results[:15]

    except Exception as shap_err:
        logger.debug(f"SHAP failed ({shap_err}), falling back to sklearn feature_importances_")
        return _sklearn_feature_importance(model, feature_names)


def _sklearn_feature_importance(model, feature_names: List[str]) -> List[Dict[str, Any]]:
    """Fall back to sklearn's built-in feature_importances_ or coef_."""
    try:
        import numpy as np
        if hasattr(model, "feature_importances_"):
            imps = model.feature_importances_
        elif hasattr(model, "coef_"):
            imps = np.abs(model.coef_[0] if model.coef_.ndim > 1 else model.coef_)
        else:
            # Named steps in pipeline
            for step in reversed(model.steps if hasattr(model, "steps") else []):
                inner = step[1]
                if hasattr(inner, "feature_importances_"):
                    imps = inner.feature_importances_
                    break
                elif hasattr(inner, "coef_"):
                    imps = np.abs(inner.coef_[0] if inner.coef_.ndim > 1 else inner.coef_)
                    break
            else:
                return []

        total = imps.sum() or 1
        results = []
        for feat, imp in zip(feature_names, imps):
            results.append({
                "feature": feat,
                "importance": round(float(imp / total), 4),
                "direction": "positive",
                "explanation": f"{feat} contributes {float(imp / total) * 100:.1f}% to predictions",
                "method": "sklearn",
            })
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results[:15]
    except Exception as e:
        logger.warning(f"Feature importance extraction failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
#  Transparency Decorator for Chat / NL2SQL responses
# ═══════════════════════════════════════════════════════════════

def enrich_response_with_trace(
    response: Dict[str, Any],
    trace: ThinkingTrace,
) -> Dict[str, Any]:
    """
    Inject the thinking_trace into an existing service response dict.
    The frontend can display this in a collapsible "AI Thinking" panel.
    """
    response["thinking_trace"] = {
        "sql_generated": trace.sql_generated,
        "tables_used": trace.tables_used,
        "columns_used": trace.columns_used,
        "chunks_retrieved": [
            {"text": c.get("text", "")[:200], "score": c.get("score", 0)}
            for c in trace.chunks_retrieved[:5]
        ],
        "confidence": trace.confidence_score,
        "confidence_reason": trace.confidence_reason,
        "grounding_sources": trace.grounding_sources,
        "model_used": trace.model_used,
        "timing": {
            "retrieval_ms": trace.retrieval_ms,
            "generation_ms": trace.generation_ms,
            "total_ms": trace.total_ms,
        },
    }
    return response
