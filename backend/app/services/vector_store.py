"""Vector index over product embeddings.

Uses a FAISS ``IndexFlatIP`` (exact inner-product search; on L2-normalised
vectors this is cosine similarity). Exact search is the right choice for a
catalog of this size; for 100k+ products swap in ``IndexHNSWFlat`` or
``IndexIVFFlat`` behind the same interface. If FAISS is unavailable a NumPy
brute-force store with the identical interface is used.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    backend: str

    @property
    def size(self) -> int: ...

    def search(self, query: np.ndarray, k: int, allowed: Optional[set[int]] = None) -> list[tuple[int, float]]: ...


class FaissVectorStore:
    backend = "faiss"

    def __init__(self, vectors: np.ndarray) -> None:
        import faiss

        self._faiss = faiss
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        if len(vectors):
            self.index.add(vectors)

    @property
    def size(self) -> int:
        return int(self.index.ntotal)

    def search(self, query: np.ndarray, k: int, allowed: Optional[set[int]] = None) -> list[tuple[int, float]]:
        if self.size == 0 or k <= 0 or (allowed is not None and not allowed):
            return []
        q = np.ascontiguousarray(query.reshape(1, -1), dtype=np.float32)
        params = None
        if allowed is not None:
            # Restrict the search to filtered IDs inside FAISS itself.
            selector = self._faiss.IDSelectorBatch(np.fromiter(allowed, dtype=np.int64))
            params = self._faiss.SearchParameters(sel=selector)
            k = min(k, len(allowed))
        k = min(k, self.size)
        scores, ids = self.index.search(q, k, params=params)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]


class NumpyVectorStore:
    backend = "numpy"

    def __init__(self, vectors: np.ndarray) -> None:
        self.vectors = np.asarray(vectors, dtype=np.float32)

    @property
    def size(self) -> int:
        return int(self.vectors.shape[0])

    def search(self, query: np.ndarray, k: int, allowed: Optional[set[int]] = None) -> list[tuple[int, float]]:
        if self.size == 0 or k <= 0:
            return []
        scores = self.vectors @ query.astype(np.float32)
        order = np.argsort(-scores)
        if allowed is not None:
            order = [i for i in order if int(i) in allowed]
        return [(int(i), float(scores[i])) for i in order[:k]]


def create_vector_store(vectors: np.ndarray) -> tuple[VectorStore, Optional[str]]:
    """Return (store, fallback_reason)."""
    try:
        return FaissVectorStore(vectors), None
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
        logger.error("FAISS unavailable (%s); using NumPy brute-force search.", reason)
        return NumpyVectorStore(vectors), reason
