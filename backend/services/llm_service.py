"""
LLM Service — backward-compatible shim over the multi-model LLMRouter.

All existing callers continue to work unchanged.  The router handles
provider selection, circuit breaking, caching, and streaming internally.
"""

import json
import re
import logging
from typing import Optional, List, Dict

from services.llm_router import llm_router

logger = logging.getLogger(__name__)


class LLMService:
    """
    Thin compatibility wrapper around LLMRouter.
    Use llm_router directly for new code that needs task-type routing.
    """

    def __init__(self):
        self._router = llm_router
        status = self._router.get_models_status()
        available = [m["name"] for m in status if m["healthy"]]
        logger.info(f"LLMService initialised — available models: {available or ['rule-based fallback']}")

    @property
    def openai_available(self) -> bool:
        return self._router._provider_available.get("openai", False)

    @property
    def ollama_available(self) -> bool:
        return self._router._provider_available.get("ollama", False)

    def complete(self, system: str, user: str, max_tokens: int = 500, task_type: str = "default") -> str:
        """Synchronous completion — routes to the best available model."""
        return self._router.complete(system, user, max_tokens, task_type=task_type)

    def generate_analysis_narrative(self, question: str, intent: str, insights: List[Dict], context: str) -> str:
        system = (
            "You are an expert data analyst AI. Generate a clear, professional, and actionable "
            "analysis narrative. Be specific with numbers when available. Use markdown formatting. "
            "Keep it concise but insightful (2-4 sentences max)."
        )
        user = f"Question: {question}\nIntent: {intent}\nContext: {context}\nInsights: {json.dumps(insights[:3])}"
        return self._router.complete(system, user, max_tokens=300, task_type="narrative")

    def generate_analysis_code(self, question: str, context: str) -> Optional[str]:
        system = (
            "You are a Python data analyst. Generate clean, safe pandas code to answer the user's question. "
            "The dataframe is available as 'df'. Store your final result in a variable called 'result'. "
            "Use only: pandas (pd), numpy (np), basic Python builtins. "
            "Do NOT import os, sys, subprocess, open files, or make network requests. "
            "Return ONLY the code, no explanation."
        )
        user = f"DataFrame context: {context}\nQuestion: {question}"
        code = self._router.complete(system, user, max_tokens=400, task_type="code")
        if code and "```" in code:
            match = re.search(r"```(?:python)?\n?(.*?)```", code, re.DOTALL)
            if match:
                code = match.group(1)
        return code if code else None

    def generate_dashboard_layout(self, command: str, columns: List[str], col_types: Dict) -> Dict:
        system = "You are a dashboard design AI. Return a JSON layout for a data dashboard."
        user = f"Command: {command}\nColumns: {columns}\nTypes: {col_types}"
        response = self._router.complete(system, user, max_tokens=600, task_type="dashboard")
        try:
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return {"title": command, "chart_types": ["bar", "line", "scatter"]}
