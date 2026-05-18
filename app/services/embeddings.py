"""
BGE-small-en-v1.5 embeddings via fastembed (ONNX, CPU-only, no GPU needed).

The model (~130 MB) downloads to ~/.cache/fastembed on first use.
Subsequent calls are instant — model stays in memory for the process lifetime.
"""
from __future__ import annotations

import numpy as np

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def embed(text: str) -> list[float]:
    """Return BGE-M3 embedding for a single text string."""
    model = _get_model()
    return next(model.embed([text])).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    av, bv = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(av) * np.linalg.norm(bv)
    return float(np.dot(av, bv) / denom) if denom > 0 else 0.0


def top_k(
    query_embedding: list[float],
    chunks: list[dict],
    k: int = 3,
) -> list[str]:
    """
    chunks: list of {"text": str, "embedding": list[float]}
    Returns the top-k chunk texts by cosine similarity to query_embedding.
    """
    scored = [
        (cosine_similarity(query_embedding, c["embedding"]), c["text"])
        for c in chunks
        if c.get("embedding")
    ]
    scored.sort(reverse=True)
    return [text for _, text in scored[:k]]
