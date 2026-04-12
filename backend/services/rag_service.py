"""
Agentic RAG Service — Retrieval-Augmented Generation for enterprise data chat.

Architecture: Corrective RAG (CRAG) pattern
  1. Index dataset content into vector chunks (sentence-transformers embeddings)
  2. Retrieve top-K relevant chunks for a question
  3. Grade relevance of retrieved chunks
  4. If low relevance → fallback to full DataFrame stats
  5. Generate answer with retrieved context
  6. Self-verify: ensure answer is grounded in the retrieved context

Storage (auto-selected at runtime):
  - PostgreSQL + pgvector  →  <=> cosine operator for native vector search (preferred)
  - SQLite fallback        →  numpy arrays persisted to disk
"""

import os
import json
import logging
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
RAG_INDEX_DIR = Path(UPLOAD_DIR) / "rag_indexes"
RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOP_K = 6
RELEVANCE_THRESHOLD = 0.30   # cosine similarity — below this = low relevance


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b) + 1e-10)
    return float(np.dot(a_norm, b_norm))


def _batch_cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Vectorised cosine similarity: query (D,) against matrix (N, D) → (N,)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    normed = matrix / norms
    q_norm = query / (np.linalg.norm(query) + 1e-10)
    return normed @ q_norm


# ── Embedding model (lazy-loaded once) ──────────────────────────
_encoder = None

def get_encoder():
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"RAG encoder loaded: {EMBEDDING_MODEL}")
        except ImportError:
            logger.warning("sentence-transformers not installed — RAG disabled")
    return _encoder


def embed(texts: List[str]) -> Optional[np.ndarray]:
    """Return (N, D) embedding matrix or None if encoder unavailable."""
    enc = get_encoder()
    if enc is None:
        return None
    return np.array(enc.encode(texts, show_progress_bar=False), dtype=np.float32)


# ── Chunk generation ─────────────────────────────────────────────

def _df_to_chunks(df: pd.DataFrame, dataset_name: str, chunk_size: int = 5) -> List[Dict]:
    """
    Convert a DataFrame into text chunks suitable for embedding.
    Each chunk = chunk_size rows serialised as a readable sentence.
    """
    chunks = []

    # 1. Column-level summaries
    for col in df.columns:
        s = df[col]
        if s.dtype in [object, "string"]:
            top = s.value_counts().head(5).to_dict()
            text = f"Column '{col}' (categorical): top values are {top}. Total {len(s)} rows, {s.isna().sum()} missing."
        elif "datetime" in str(s.dtype):
            text = f"Column '{col}' (date): ranges from {s.min()} to {s.max()}."
        else:
            text = (
                f"Column '{col}' (numeric): mean={s.mean():.4g}, "
                f"median={s.median():.4g}, std={s.std():.4g}, "
                f"min={s.min():.4g}, max={s.max():.4g}, "
                f"missing={s.isna().sum()}."
            )
        chunks.append({"type": "column_summary", "column": col, "text": text})

    # 2. Row chunks
    for start in range(0, min(len(df), 2000), chunk_size):
        slice_ = df.iloc[start : start + chunk_size]
        rows_text = slice_.to_string(index=False, max_cols=20)
        text = f"Rows {start}–{start + len(slice_)} of '{dataset_name}':\n{rows_text}"
        chunks.append({"type": "rows", "start": start, "text": text})

    # 3. Dataset-level overview
    overview = (
        f"Dataset '{dataset_name}' has {len(df)} rows and {len(df.columns)} columns. "
        f"Columns: {', '.join(df.columns.tolist()[:30])}. "
        f"Missing cells: {int(df.isna().sum().sum())}. "
        f"Numeric columns: {df.select_dtypes(include='number').columns.tolist()[:15]}."
    )
    chunks.insert(0, {"type": "overview", "text": overview})

    return chunks


# ── Index management ─────────────────────────────────────────────

def index_path(dataset_id: str) -> Path:
    return RAG_INDEX_DIR / dataset_id


def build_index(df: pd.DataFrame, dataset_id: str, dataset_name: str) -> bool:
    """Build and persist a vector index for a dataset. Returns True on success."""
    enc = get_encoder()
    if enc is None:
        logger.warning("Encoder not available — skipping RAG index build")
        return False

    chunks = _df_to_chunks(df, dataset_name)
    texts = [c["text"] for c in chunks]

    logger.info(f"Building RAG index for {dataset_id} — {len(chunks)} chunks")
    embeddings = embed(texts)
    if embeddings is None:
        return False

    idx_dir = index_path(dataset_id)
    idx_dir.mkdir(parents=True, exist_ok=True)

    np.save(str(idx_dir / "embeddings.npy"), embeddings)
    with open(str(idx_dir / "chunks.pkl"), "wb") as f:
        pickle.dump(chunks, f)

    logger.info(f"RAG index saved: {idx_dir}")
    return True


def load_index(dataset_id: str) -> Tuple[Optional[np.ndarray], Optional[List[Dict]]]:
    """Load persisted index. Returns (embeddings, chunks) or (None, None)."""
    idx_dir = index_path(dataset_id)
    emb_path = idx_dir / "embeddings.npy"
    chunks_path = idx_dir / "chunks.pkl"

    if not emb_path.exists() or not chunks_path.exists():
        return None, None

    embeddings = np.load(str(emb_path))
    with open(str(chunks_path), "rb") as f:
        chunks = pickle.load(f)
    return embeddings, chunks


def retrieve(
    question: str, dataset_id: str, top_k: int = TOP_K
) -> Tuple[List[Dict], float]:
    """
    Retrieve top-K most relevant chunks.
    Returns (chunks, max_similarity_score).
    """
    embeddings, chunks = load_index(dataset_id)
    if embeddings is None or chunks is None:
        return [], 0.0

    q_emb = embed([question])
    if q_emb is None:
        return [], 0.0

    scores = _batch_cosine_similarity(q_emb[0], embeddings)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for i in top_indices:
        results.append({**chunks[i], "score": float(scores[i])})

    max_score = float(scores[top_indices[0]]) if len(top_indices) > 0 else 0.0
    return results, max_score


# ── pgvector backend (PostgreSQL) ────────────────────────────────

def _pgvector_store_chunks(
    dataset_id: str,
    chunks: List[Dict],
    embeddings: np.ndarray,
    db_session,
) -> bool:
    """
    Persist chunk embeddings into PostgreSQL using the pgvector Vector column.
    Replaces any existing chunks for this dataset_id.
    Returns True on success.
    """
    try:
        from models.database import DatasetChunk, _pgvector_available
        if not _pgvector_available:
            return False

        # Delete existing chunks for this dataset
        db_session.query(DatasetChunk).filter(
            DatasetChunk.dataset_id == dataset_id
        ).delete()

        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            row = DatasetChunk(
                dataset_id=dataset_id,
                chunk_index=idx,
                chunk_type=chunk.get("type", "rows"),
                chunk_text=chunk["text"],
                metadata_={"score": 0.0, **{k: v for k, v in chunk.items() if k not in ("text", "type")}},
                embedding=emb.tolist(),
            )
            db_session.add(row)

        db_session.commit()
        logger.info(f"pgvector: stored {len(chunks)} chunks for dataset {dataset_id}")
        return True
    except Exception as e:
        logger.error(f"pgvector store error: {e}")
        try:
            db_session.rollback()
        except Exception:
            pass
        return False


def _pgvector_retrieve(
    question: str,
    dataset_id: str,
    top_k: int,
    db_session,
) -> Tuple[List[Dict], float]:
    """
    Retrieve top-K semantically similar chunks from PostgreSQL using
    pgvector's cosine_distance operator.
    cosine_distance ∈ [0, 1]  (0 = identical, 1 = orthogonal)
    similarity = 1 - distance  ∈ [0, 1]
    """
    try:
        from models.database import DatasetChunk, _pgvector_available
        if not _pgvector_available:
            return [], 0.0

        q_emb = embed([question])
        if q_emb is None:
            return [], 0.0

        q_list = q_emb[0].tolist()

        # Query text + distance separately — avoids ORM tuple unpacking ambiguity
        rows = (
            db_session.query(
                DatasetChunk.chunk_text,
                DatasetChunk.chunk_type,
                DatasetChunk.metadata_,
                DatasetChunk.embedding.cosine_distance(q_list).label("dist"),
            )
            .filter(DatasetChunk.dataset_id == dataset_id)
            .order_by("dist")
            .limit(top_k)
            .all()
        )

        if not rows:
            return [], 0.0

        chunks_out = []
        for chunk_text, chunk_type, meta, dist in rows:
            # cosine_distance in pgvector is in [0, 1]
            similarity = max(0.0, 1.0 - float(dist))
            chunks_out.append({
                **(meta or {}),        # spread first — score key may be 0.0 placeholder
                "text": chunk_text,
                "type": chunk_type or "rows",
                "score": similarity,   # always overrides with real computed similarity
            })

        max_sim = chunks_out[0]["score"] if chunks_out else 0.0
        logger.info(
            f"pgvector retrieve: {len(chunks_out)} chunks, "
            f"top_score={max_sim:.3f} for dataset {dataset_id}"
        )
        return chunks_out, max_sim

    except Exception as e:
        logger.error(f"pgvector retrieve error: {e}")
        return [], 0.0


def _pgvector_has_index(dataset_id: str, db_session) -> bool:
    """Return True if pgvector chunks exist for this dataset."""
    try:
        from models.database import DatasetChunk, _pgvector_available
        if not _pgvector_available:
            return False
        count = (
            db_session.query(DatasetChunk)
            .filter(DatasetChunk.dataset_id == dataset_id)
            .filter(DatasetChunk.embedding.is_not(None))
            .limit(1)
            .count()
        )
        return count > 0
    except Exception:
        return False


# ── CRAG Grading ─────────────────────────────────────────────────

def _grade_relevance(retrieved_chunks: List[Dict], threshold: float = RELEVANCE_THRESHOLD) -> str:
    """Return 'high' | 'medium' | 'low' based on retrieval scores."""
    if not retrieved_chunks:
        return "low"
    max_score = max(c.get("score", 0) for c in retrieved_chunks)
    if max_score >= threshold * 2:
        return "high"
    if max_score >= threshold:
        return "medium"
    return "low"


# ── Main RAG Service ─────────────────────────────────────────────

class RAGService:
    """
    Corrective RAG (CRAG) — retrieves, grades, and conditionally falls back
    to a broader analysis when retrieval confidence is low.
    """

    def __init__(self, llm_service):
        self.llm = llm_service

    def answer(
        self,
        question: str,
        dataset_id: str,
        df: Optional[pd.DataFrame] = None,
        dataset_name: str = "dataset",
        chat_history: Optional[List[Dict]] = None,
        db_session=None,
    ) -> Dict[str, Any]:
        """
        Answer a question using RAG.

        Uses pgvector (PostgreSQL) when db_session is provided and pgvector
        is available; otherwise falls back to numpy-based file retrieval.

        Returns:
          - answer (str): AI-generated response
          - sources (list[dict]): retrieved chunk references
          - confidence (str): high | medium | low
          - used_rag (bool): whether vector retrieval was used
          - backend (str): "pgvector" | "numpy"
        """
        # 1. Retrieve context — pgvector preferred, numpy fallback
        backend = "numpy"
        if db_session is not None:
            try:
                from models.database import _pgvector_available
                if _pgvector_available:
                    retrieved, max_score = _pgvector_retrieve(question, dataset_id, TOP_K, db_session)
                    backend = "pgvector"
                else:
                    retrieved, max_score = retrieve(question, dataset_id, top_k=TOP_K)
            except Exception as e:
                logger.warning(f"pgvector retrieve failed, falling back to numpy: {e}")
                retrieved, max_score = retrieve(question, dataset_id, top_k=TOP_K)
        else:
            retrieved, max_score = retrieve(question, dataset_id, top_k=TOP_K)

        confidence = _grade_relevance(retrieved, RELEVANCE_THRESHOLD)
        logger.info(
            f"RAG [{backend}] retrieval: {len(retrieved)} chunks, "
            f"max_score={max_score:.3f}, confidence={confidence}"
        )

        # 2. Build context string from retrieved chunks
        context_parts = []
        if retrieved:
            for i, chunk in enumerate(retrieved[:TOP_K]):
                context_parts.append(f"[Source {i+1}] {chunk['text']}")
            context_str = "\n\n".join(context_parts)
        else:
            context_str = ""

        # 3. If low confidence and we have the DataFrame, enrich context with quick stats
        if confidence == "low" and df is not None:
            logger.info("RAG confidence low — enriching with live DataFrame stats")
            context_str += self._quick_stats_context(df, dataset_name)

        # 4. Build history string
        history_str = ""
        if chat_history:
            recent = chat_history[-4:]  # Last 4 turns
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:200]
                history_str += f"{role.capitalize()}: {content}\n"

        # 5. Generate answer
        system = """You are an expert AI data analyst. Answer the user's question using ONLY the provided context.
Be specific with numbers, trends, and patterns you observe. Use markdown for formatting.
If the context doesn't contain enough information to answer fully, say so and provide what you can.
Do not fabricate data points that aren't in the context."""

        user_prompt = f"""Dataset: {dataset_name}

Context from the data:
{context_str}

{f"Conversation history:{chr(10)}{history_str}" if history_str else ""}

User Question: {question}

Answer:"""

        answer = self.llm.complete(system, user_prompt, max_tokens=600)

        # 6. Self-verification (Corrective RAG step)
        if confidence == "high":
            answer = self._verify_answer(question, answer, context_str)

        return {
            "answer": answer,
            "sources": [{"text": c["text"][:200], "score": c.get("score", 0), "type": c.get("type", "")} for c in retrieved[:3]],
            "confidence": confidence,
            "used_rag": len(retrieved) > 0,
            "retrieval_score": max_score,
            "backend": backend,
        }

    def _quick_stats_context(self, df: pd.DataFrame, name: str) -> str:
        """Generate a quick statistical summary when RAG confidence is low."""
        num_cols = df.select_dtypes(include="number").columns.tolist()
        lines = [f"\n\nLive stats for '{name}':"]
        for col in num_cols[:8]:
            lines.append(
                f"  {col}: mean={df[col].mean():.4g}, "
                f"min={df[col].min():.4g}, max={df[col].max():.4g}"
            )
        return "\n".join(lines)

    def _verify_answer(self, question: str, answer: str, context: str) -> str:
        """
        Corrective step: check if the answer is grounded in context.
        If not, ask the LLM to revise.
        """
        verify_prompt = f"""You generated this answer to the question: "{question}"

Answer: {answer[:500]}

Context used:
{context[:800]}

Is the answer fully grounded in the context? If not, revise it to only include supported claims.
Output the final verified answer only, no explanation."""

        verified = self.llm.complete(
            "You are a fact-checker for AI-generated data analysis answers.",
            verify_prompt,
            max_tokens=600,
        )
        return verified if verified else answer

    def ensure_index(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        dataset_name: str,
        db_session=None,
    ) -> bool:
        """
        Build and persist vector index if not already present.

        Stores in PostgreSQL (pgvector) when db_session provided AND
        pgvector is available; otherwise persists as numpy files.
        """
        # ── pgvector path ──────────────────────────────────────────
        if db_session is not None:
            try:
                from models.database import _pgvector_available
                if _pgvector_available and _pgvector_has_index(dataset_id, db_session):
                    logger.info(f"pgvector index already exists for {dataset_id}")
                    return True
                if _pgvector_available:
                    chunks = _df_to_chunks(df, dataset_name)
                    texts = [c["text"] for c in chunks]
                    embeddings = embed(texts)
                    if embeddings is not None:
                        return _pgvector_store_chunks(dataset_id, chunks, embeddings, db_session)
            except Exception as e:
                logger.warning(f"pgvector index build failed, falling back to numpy: {e}")

        # ── numpy fallback ─────────────────────────────────────────
        embeddings, _ = load_index(dataset_id)
        if embeddings is not None:
            return True
        return build_index(df, dataset_id, dataset_name)
