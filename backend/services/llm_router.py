"""
Multi-Model LLM Router — intelligently routes requests to the best AI model
based on task type, cost, latency, and availability.

Supported providers:
  - OpenAI  (GPT-4o, GPT-4o-mini)
  - Anthropic Claude (claude-sonnet-4-5)
  - Google Gemini (gemini-1.5-pro, gemini-1.5-flash)
  - Ollama  (local fallback)

Routing rules:
  - sql / code / structured  → GPT-4o (best structured output)
  - narrative / story / explain → Claude Sonnet (best prose)
  - large_context / rag      → Gemini 1.5 Pro (2M token context)
  - default / cheap          → GPT-4o-mini
"""

import os
import time
import hashlib
import logging
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional, List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "llama3")
USE_OLLAMA         = os.getenv("USE_OLLAMA", "false").lower() == "true"
# Allow overriding the Anthropic model via env (defaults to haiku for cost efficiency)
ANTHROPIC_LLM_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Redis for LLM response caching (optional)
REDIS_URL          = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# ── Model configuration ───────────────────────────────────────────

@dataclass
class ModelConfig:
    name: str
    provider: str                    # openai | anthropic | google | ollama
    model_id: str                    # actual API model name
    cost_per_1k_tokens: float        # USD, rough estimate
    max_context: int                 # max input tokens
    strengths: List[str]             # task tags this model excels at
    available: bool = True


# Task-type → model routing table
TASK_ROUTING: Dict[str, str] = {
    "sql":         "gpt-4o",
    "code":        "gpt-4o",
    "structured":  "gpt-4o",
    "nl2sql":      "gpt-4o",
    "narrative":   "claude-sonnet",
    "story":       "claude-sonnet",
    "explain":     "claude-sonnet",
    "report":      "claude-sonnet",
    "large_context":"gemini-pro",
    "rag":         "gemini-pro",
    "default":     "gpt-4o-mini",
    "chat":        "gpt-4o-mini",
    "summary":     "gpt-4o-mini",
    "insight":     "gpt-4o-mini",
    "forecast":    "gpt-4o-mini",
    "anomaly":     "gpt-4o-mini",
    "root_cause":  "claude-sonnet",
    "automl":      "gpt-4o-mini",
    "dashboard":   "gpt-4o",
}

ALL_MODELS: Dict[str, ModelConfig] = {
    "gpt-4o": ModelConfig(
        name="GPT-4o",
        provider="openai",
        model_id="gpt-4o",
        cost_per_1k_tokens=0.005,
        max_context=128_000,
        strengths=["sql", "code", "structured", "nl2sql", "dashboard"],
    ),
    "gpt-4o-mini": ModelConfig(
        name="GPT-4o Mini",
        provider="openai",
        model_id="gpt-4o-mini",
        cost_per_1k_tokens=0.00015,
        max_context=128_000,
        strengths=["default", "chat", "summary", "insight", "fast"],
    ),
    "claude-sonnet": ModelConfig(
        name="Claude (Anthropic)",
        provider="anthropic",
        model_id=ANTHROPIC_LLM_MODEL,
        cost_per_1k_tokens=0.00025,
        max_context=200_000,
        strengths=["narrative", "story", "explain", "report", "root_cause"],
    ),
    "gemini-pro": ModelConfig(
        name="Gemini 1.5 Pro",
        provider="google",
        model_id="gemini-1.5-pro",
        cost_per_1k_tokens=0.00125,
        max_context=2_000_000,
        strengths=["large_context", "rag", "multimodal"],
    ),
    "gemini-flash": ModelConfig(
        name="Gemini 1.5 Flash",
        provider="google",
        model_id="gemini-1.5-flash",
        cost_per_1k_tokens=0.000075,
        max_context=1_000_000,
        strengths=["fast", "cheap"],
    ),
    "ollama": ModelConfig(
        name="Ollama (Local)",
        provider="ollama",
        model_id=OLLAMA_MODEL,
        cost_per_1k_tokens=0.0,
        max_context=8_000,
        strengths=["private", "offline"],
    ),
}


class LLMRouter:
    """
    Central multi-model LLM router with circuit breaker,
    Redis response caching, and SSE streaming support.
    """

    def __init__(self):
        # Track per-model consecutive failures for circuit breaker
        self._failure_counts: Dict[str, int] = {}
        self._circuit_open_until: Dict[str, datetime] = {}

        # Detect which providers are actually configured
        self._provider_available: Dict[str, bool] = {
            "openai":    bool(OPENAI_API_KEY),
            "anthropic": bool(ANTHROPIC_API_KEY),
            "google":    bool(GEMINI_API_KEY),
            "ollama":    self._check_ollama(),
        }
        logger.info(f"LLMRouter providers: {self._provider_available}")

        # Try to connect to Redis for response caching
        self._redis = None
        self._init_redis()

    def _check_ollama(self) -> bool:
        try:
            import httpx
            resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            self._redis.ping()
        except Exception:
            self._redis = None

    # ── Circuit breaker ──────────────────────────────────────────

    def _is_circuit_open(self, model_key: str) -> bool:
        until = self._circuit_open_until.get(model_key)
        if until and datetime.utcnow() < until:
            return True
        return False

    def _record_failure(self, model_key: str):
        count = self._failure_counts.get(model_key, 0) + 1
        self._failure_counts[model_key] = count
        if count >= 3:
            self._circuit_open_until[model_key] = datetime.utcnow() + timedelta(minutes=5)
            logger.warning(f"Circuit breaker OPEN for {model_key} — pausing 5 minutes")

    def _record_success(self, model_key: str):
        self._failure_counts[model_key] = 0
        self._circuit_open_until.pop(model_key, None)

    # ── Model selection ──────────────────────────────────────────

    def route(self, task_type: str = "default", prompt_tokens: int = 0) -> ModelConfig:
        """Pick the best available model for a given task type."""
        preferred_key = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

        # For large context tasks, prefer gemini regardless
        if prompt_tokens > 50_000:
            preferred_key = "gemini-pro"

        # Try preferred, then fall back through alternatives
        fallback_order = [preferred_key, "gpt-4o-mini", "claude-sonnet", "gemini-flash", "ollama"]

        for key in fallback_order:
            cfg = ALL_MODELS.get(key)
            if not cfg:
                continue
            if not self._provider_available.get(cfg.provider, False):
                continue
            if self._is_circuit_open(key):
                continue
            return cfg

        # Absolute fallback — rule-based (no LLM)
        return ModelConfig(
            name="Rule-based", provider="none", model_id="none",
            cost_per_1k_tokens=0, max_context=0, strengths=[]
        )

    # ── Redis cache ──────────────────────────────────────────────

    def _cache_key(self, system: str, user: str) -> str:
        h = hashlib.sha256(f"{system}||{user}".encode()).hexdigest()
        return f"llm:{h}"

    def _get_cached(self, system: str, user: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return self._redis.get(self._cache_key(system, user))
        except Exception:
            return None

    def _set_cached(self, system: str, user: str, response: str):
        if not self._redis:
            return
        try:
            self._redis.setex(self._cache_key(system, user), 3600, response)
        except Exception:
            pass

    # ── Sync completion (backward-compatible) ────────────────────

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 500,
        task_type: str = "default",
        use_cache: bool = True,
    ) -> str:
        """Synchronous completion — drops into the best available model."""
        if use_cache:
            cached = self._get_cached(system, user)
            if cached:
                return cached

        cfg = self.route(task_type, prompt_tokens=len(system) + len(user))

        start = time.time()
        result = ""
        try:
            if cfg.provider == "openai":
                result = self._complete_openai(cfg.model_id, system, user, max_tokens)
            elif cfg.provider == "anthropic":
                result = self._complete_anthropic(cfg.model_id, system, user, max_tokens)
            elif cfg.provider == "google":
                result = self._complete_google(cfg.model_id, system, user, max_tokens)
            elif cfg.provider == "ollama":
                result = self._complete_ollama(system, user, max_tokens)
            else:
                result = self._rule_based(system, user)

            self._record_success(cfg.model_id)
            if use_cache and result:
                self._set_cached(system, user, result)
            self._log_usage(cfg, system, user, result, time.time() - start, success=True)
            return result

        except Exception as e:
            logger.error(f"LLM error ({cfg.name}): {e}")
            self._record_failure(cfg.model_id)
            self._log_usage(cfg, system, user, "", time.time() - start, success=False)
            # Retry with next available model
            return self._fallback_complete(system, user, max_tokens, exclude=cfg.provider)

    def _fallback_complete(self, system: str, user: str, max_tokens: int, exclude: str) -> str:
        """Try remaining providers when the primary fails."""
        for key in ["gpt-4o-mini", "claude-sonnet", "gemini-flash", "ollama"]:
            cfg = ALL_MODELS.get(key)
            if not cfg or cfg.provider == exclude:
                continue
            if not self._provider_available.get(cfg.provider, False):
                continue
            try:
                if cfg.provider == "openai":
                    return self._complete_openai(cfg.model_id, system, user, max_tokens)
                elif cfg.provider == "anthropic":
                    return self._complete_anthropic(cfg.model_id, system, user, max_tokens)
                elif cfg.provider == "google":
                    return self._complete_google(cfg.model_id, system, user, max_tokens)
                elif cfg.provider == "ollama":
                    return self._complete_ollama(system, user, max_tokens)
            except Exception as e:
                logger.error(f"Fallback {cfg.name} failed: {e}")
        return self._rule_based(system, user)

    # ── Provider implementations ─────────────────────────────────

    def _complete_openai(self, model_id: str, system: str, user: str, max_tokens: int) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

    def _complete_anthropic(self, model_id: str, system: str, user: str, max_tokens: int) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text if msg.content else ""

    def _complete_google(self, model_id: str, system: str, user: str, max_tokens: int) -> str:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=model_id,
            system_instruction=system,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.3},
        )
        resp = model.generate_content(user)
        return resp.text or ""

    def _complete_ollama(self, system: str, user: str, max_tokens: int) -> str:
        import httpx
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": f"{system}\n\n{user}", "stream": False},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
        return ""

    # ── Async streaming (SSE) ────────────────────────────────────

    async def stream_complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000,
        task_type: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding tokens for SSE streaming."""
        cfg = self.route(task_type)

        try:
            if cfg.provider == "openai":
                async for token in self._stream_openai(cfg.model_id, system, user, max_tokens):
                    yield token
            elif cfg.provider == "anthropic":
                async for token in self._stream_anthropic(cfg.model_id, system, user, max_tokens):
                    yield token
            elif cfg.provider == "google":
                # Gemini doesn't have great async streaming — run sync in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, self._complete_google, cfg.model_id, system, user, max_tokens
                )
                for word in result.split():
                    yield word + " "
                    await asyncio.sleep(0.01)
            else:
                # Fallback: yield full response at once
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self.complete, system, user, max_tokens, task_type, False)
                yield result
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self._record_failure(cfg.model_id)
            yield f"[Error: {str(e)}]"

    async def _stream_openai(self, model_id: str, system: str, user: str, max_tokens: int) -> AsyncGenerator[str, None]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    async def _stream_anthropic(self, model_id: str, system: str, user: str, max_tokens: int) -> AsyncGenerator[str, None]:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model=model_id,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    # ── Rule-based fallback ──────────────────────────────────────

    def _rule_based(self, system: str, user: str) -> str:
        """Intelligent rule-based fallback that parses context and generates data-driven responses."""
        import re as _re

        s_low = system.lower()
        u_low = user.lower()

        # ── SQL generation ──────────────────────────────────────────
        if "sql" in s_low or "select" in s_low:
            # Try to extract table/column hints from user prompt
            table_match = _re.search(r'from\s+["\']?(\w+)["\']?', u_low)
            table = table_match.group(1) if table_match else "data"
            return f"SELECT * FROM {table} LIMIT 100"

        # ── Code generation ──────────────────────────────────────────
        if "code" in s_low or "python" in s_low:
            return "result = df.describe()\nprint(result)"

        # ── Root cause analysis narrative ─────────────────────────────
        if "root cause" in s_low:
            metric_match = _re.search(r"metric ['\"]([^'\"]+)['\"]", user)
            change_match = _re.search(r"(increased|decreased) by ([\d.]+)%", user)
            drivers_match = _re.search(r"Top correlated variables:\s*(.+?)(?:\n|$)", user)
            segments_match = _re.search(r"Most affected segments:\s*(.+?)(?:\n|$)", user)
            metric_name = metric_match.group(1) if metric_match else "the metric"
            direction = change_match.group(1) if change_match else "changed"
            change_val = change_match.group(2) if change_match else ""
            drivers = drivers_match.group(1).strip() if drivers_match else "no strong correlating variables identified"
            segments = segments_match.group(1).strip() if segments_match else "no significant segment variations"
            change_str = f" by **{change_val}%**" if change_val else ""
            return (
                f"**{metric_name}** has {direction}{change_str} over the analysis period. "
                f"The most correlated factors are: {drivers}. "
                f"Segment analysis highlights: {segments}. "
                "Investigate these variables for the same time period to identify causal relationships."
            )

        # ── Business recommendation ───────────────────────────────────
        if "business analyst" in s_low or ("recommendation" in s_low and "finding" in u_low):
            finding_match = _re.search(r"Finding:\s*(.+?)(?:\n|$)", user)
            desc_match = _re.search(r"Description:\s*(.+?)(?:\n|$)", user)
            finding = finding_match.group(1).strip() if finding_match else ""
            desc = desc_match.group(1).strip() if desc_match else ""
            if finding:
                desc_snippet = (desc[:80] + "…") if desc and len(desc) > 80 else desc
                return (
                    f"For '{finding}': {desc_snippet or 'Review the underlying data for this trend.'} "
                    "Implement targeted corrective actions and monitor the metric weekly to track improvement."
                )

        # ── Narrative / insight generation ───────────────────────────
        if any(k in s_low for k in ("insight", "narrative", "story", "analyst", "analysis")):
            return self._build_narrative_from_context(user)

        return self._build_narrative_from_context(user)

    def _build_narrative_from_context(self, user: str) -> str:
        """Parse dataset context embedded in the user prompt and build a real narrative."""
        import re as _re

        lines = user.split("\n")
        question = ""
        intent = ""
        rows, cols = 0, 0
        col_names: list = []
        insights: list = []

        for line in lines:
            low = line.lower().strip()
            if low.startswith("question:"):
                question = line.split(":", 1)[1].strip()
            elif low.startswith("intent:"):
                intent = line.split(":", 1)[1].strip()
            elif "rows" in low and "columns" in low:
                m = _re.search(r"(\d[\d,]*)\s*rows.*?(\d+)\s*col", low)
                if m:
                    rows = int(m.group(1).replace(",", ""))
                    cols = int(m.group(2))
            elif low.startswith("columns:"):
                col_names = [c.strip() for c in line.split(":", 1)[1].split(",")[:10]]
            elif low.startswith("-") and ":" in line:
                insights.append(line.strip("- ").strip())

        # Greeting / conversational — only trigger for explicit greetings, not missing question
        if question and question.lower() in ("hi", "hello", "hey", "how are you", "help"):
            return (
                "Hello! I'm your AI data analyst. I can help you explore your dataset — "
                "try asking me things like:\n"
                "- *'Give me a summary of the data'*\n"
                "- *'Show me correlations between columns'*\n"
                "- *'What are the top 10 rows by sales?'*\n"
                "- *'Are there any outliers?'*"
            )

        # Build context-aware response
        parts: list = []

        if question:
            parts.append(f"Regarding your question: **\"{question}\"**\n")

        if rows and cols:
            parts.append(f"Your dataset has **{rows:,} rows** and **{cols} columns**.")

        if col_names:
            parts.append(f"Available columns include: {', '.join(f'`{c}`' for c in col_names[:8])}.")

        if insights:
            parts.append("\n**Key findings from the analysis:**")
            for ins in insights[:5]:
                parts.append(f"- {ins}")

        # Intent-specific guidance
        if intent == "generic" or not intent:
            if rows:
                parts.append(
                    f"\nWith {rows:,} records, I recommend starting with a summary or distribution analysis. "
                    "Try asking: *'Show me the distribution of [column name]'* or *'What are the top values?'*"
                )
            else:
                parts.append(
                    "\nTry asking for a summary, correlations, trends, or top-N analysis to get started."
                )

        if not parts:
            return (
                "I've processed your request. Try asking for a data summary, "
                "correlations, distributions, trends, or outlier detection for detailed insights."
            )

        return "\n".join(parts)

    # ── Usage logging ────────────────────────────────────────────

    def _log_usage(
        self,
        cfg: ModelConfig,
        system: str,
        user: str,
        response: str,
        latency_s: float,
        success: bool,
    ):
        try:
            # Rough token count: ~4 chars per token
            prompt_tokens = (len(system) + len(user)) // 4
            completion_tokens = len(response) // 4
            cost_usd = (prompt_tokens + completion_tokens) / 1000 * cfg.cost_per_1k_tokens
            logger.debug(
                f"LLM [{cfg.name}] tokens={prompt_tokens}+{completion_tokens} "
                f"cost=${cost_usd:.5f} latency={latency_s*1000:.0f}ms success={success}"
            )
        except Exception:
            pass

    # ── Model health status ──────────────────────────────────────

    def get_models_status(self) -> List[Dict[str, Any]]:
        """Return all models with their current health and availability."""
        result = []
        for key, cfg in ALL_MODELS.items():
            is_available = self._provider_available.get(cfg.provider, False)
            circuit_open = self._is_circuit_open(key)
            result.append({
                "key": key,
                "name": cfg.name,
                "provider": cfg.provider,
                "model_id": cfg.model_id,
                "cost_per_1k_tokens": cfg.cost_per_1k_tokens,
                "max_context": cfg.max_context,
                "strengths": cfg.strengths,
                "api_key_configured": is_available,
                "circuit_breaker_open": circuit_open,
                "healthy": is_available and not circuit_open,
            })
        return result


# ── Singleton ─────────────────────────────────────────────────────
llm_router = LLMRouter()
