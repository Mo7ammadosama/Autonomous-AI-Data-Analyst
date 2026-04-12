"""
AgentMemoryService — persistent per-user memory for the DataMind agent.

Memories are extracted after each run via LLM and stored in the agent_memories table.
They are injected into the system prompt at the start of each new run to personalise
the analysis and learn from past corrections.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AgentMemoryService:

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_user_memories(db: Session, user_id: str, limit: int = 5) -> str:
        """
        Return top `limit` memories (by importance desc, access_count desc) as
        a formatted string suitable for injection into the system prompt.
        """
        from models.database import AgentMemory

        memories = (
            db.query(AgentMemory)
            .filter(AgentMemory.user_id == user_id)
            .order_by(AgentMemory.importance.desc(), AgentMemory.access_count.desc())
            .limit(limit)
            .all()
        )

        if not memories:
            return ""

        lines = []
        for m in memories:
            lines.append(f"[{m.memory_type.upper()}] {m.key}: {m.value}")
            # Bump access count (non-critical, ignore errors)
            try:
                m.access_count = (m.access_count or 0) + 1
                db.commit()
            except Exception:
                pass

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Extract & save after a run                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_and_save_memories(
        db: Session,
        user_id: str,
        run_id: str,
        task: str,
        steps: list[dict],
        summary: str,
        duration_seconds: float = 999,
    ) -> None:
        """
        Call the LLM to extract domain knowledge, KPI preferences, and analysis
        patterns from a completed run, then save them as AgentMemory records.
        Designed to be called in a background thread (non-blocking from the agent loop).
        """
        from models.database import AgentMemory

        if duration_seconds is None or duration_seconds < 60:
            return

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

            # Build a compact representation of the run
            step_summary = "\n".join(
                f"Step {s.get('iteration', '')}: {s.get('action', '')} — {str(s.get('observation', ''))[:200]}"
                for s in steps[:8]
            )

            prompt = f"""You are a memory extraction system. Analyse this data analysis session and extract
useful memories the agent should retain for this user's future analyses.

TASK: {task}

STEPS TAKEN:
{step_summary}

FINAL SUMMARY (first 500 chars):
{summary[:500]}

Extract 3-6 memories. For each, output a JSON object with:
- memory_type: one of "preference", "domain_knowledge", "past_analysis"
- key: short label (max 50 chars)
- value: the memory content (max 200 chars)
- importance: float 0.5-2.0 (higher = more important)

Respond with a JSON array only, like: [{{"memory_type": "...", "key": "...", "value": "...", "importance": 1.0}}]
No other text, no wrapper object."""

            resp = client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "["},
                ],
                max_tokens=800,
                temperature=0,
            )

            raw = "[" + (resp.content[0].text if resp.content else "]")
            # The model may return {"memories": [...]} or just [...]
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                items = parsed.get("memories", parsed.get("data", list(parsed.values())[0] if parsed else []))
            else:
                items = parsed

            if not isinstance(items, list):
                return

            saved = 0
            for item in items[:6]:
                if not isinstance(item, dict):
                    continue
                mem = AgentMemory(
                    user_id=user_id,
                    memory_type=item.get("memory_type", "past_analysis"),
                    key=str(item.get("key", ""))[:100],
                    value=str(item.get("value", ""))[:500],
                    source_run_id=run_id,
                    importance=float(item.get("importance", 1.0)),
                )
                db.add(mem)
                saved += 1

            db.commit()
            logger.info(f"Saved {saved} memories from run {run_id} for user {user_id}")

        except Exception as exc:
            logger.warning(f"Memory extraction failed for run {run_id}: {exc}")
            try:
                db.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Save correction                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def save_correction(
        db: Session,
        user_id: str,
        run_id: Optional[str],
        correction_text: str,
    ) -> None:
        """Save a user-provided correction as a high-importance memory."""
        from models.database import AgentMemory

        mem = AgentMemory(
            user_id=user_id,
            memory_type="correction",
            key=f"User correction {datetime.utcnow().strftime('%Y-%m-%d')}",
            value=correction_text[:500],
            source_run_id=run_id,
            importance=2.0,   # corrections are most important
        )
        db.add(mem)
        db.commit()

    # ------------------------------------------------------------------ #
    #  Search                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def search_memories(db: Session, user_id: str, query: str) -> list:
        """Keyword search over memory keys and values."""
        from models.database import AgentMemory
        from sqlalchemy import or_

        q = f"%{query.lower()}%"
        memories = (
            db.query(AgentMemory)
            .filter(
                AgentMemory.user_id == user_id,
                or_(
                    AgentMemory.key.ilike(q),
                    AgentMemory.value.ilike(q),
                ),
            )
            .order_by(AgentMemory.importance.desc())
            .limit(20)
            .all()
        )
        return memories
