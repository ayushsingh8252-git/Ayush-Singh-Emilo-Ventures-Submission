"""Text encoders.

``SentenceTransformerEncoder`` is the primary (semantic) encoder. If the model
cannot be loaded (no internet on first run, missing package, ...) or the
fallback is forced, ``TfidfEncoder`` is used instead. The active mode is
always reported by ``/api/health`` - the fallback never pretends to be
semantic.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional, Protocol

import numpy as np

from app.services.preprocessing import tokenize

logger = logging.getLogger(__name__)

MODE_SEMANTIC = "semantic"
MODE_TFIDF = "tfidf_fallback"


class Encoder(Protocol):
    mode: str
    name: str
    # Cosine similarities are mapped linearly from [floor, ceil] to [0, 1];
    # the two encoders produce very differently distributed similarities.
    semantic_floor: float
    semantic_ceil: float

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class SentenceTransformerEncoder:
    mode = MODE_SEMANTIC
    # all-MiniLM-L6-v2: unrelated text pairs typically score < 0.15 and
    # clearly related pairs 0.45-0.65 (measured on this catalog).
    semantic_floor = 0.10
    semantic_ceil = 0.60

    def __init__(self, model_name: str, cache_dir: Optional[Path] = None, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, kept local

        self.name = model_name
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        self.model = SentenceTransformer(model_name, device="cpu")

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode_corpus(self, texts: list[str]) -> np.ndarray:
        """Batch-encode a corpus, reusing an on-disk cache keyed by content."""
        if self.cache_dir is None:
            return self.encode(texts)
        digest = hashlib.sha256(("\x1f".join([self.name, *texts])).encode("utf-8")).hexdigest()[:24]
        path = Path(self.cache_dir) / f"embeddings_{digest}.npy"
        if path.exists():
            try:
                cached = np.load(path)
                if cached.shape[0] == len(texts):
                    logger.info("Loaded %d cached embeddings from %s", len(texts), path.name)
                    return cached.astype(np.float32)
            except (OSError, ValueError) as exc:
                logger.warning("Ignoring unreadable embedding cache %s: %s", path, exc)
        vectors = self.encode(texts)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, vectors)
        except OSError as exc:
            logger.warning("Could not write embedding cache: %s", exc)
        return vectors


class TfidfEncoder:
    """Lexical fallback: TF-IDF (unigrams + bigrams) over stemmed tokens."""

    mode = MODE_TFIDF
    name = "tfidf (scikit-learn)"
    semantic_floor = 0.0
    semantic_ceil = 0.35

    def __init__(self, corpus: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer: Optional[TfidfVectorizer] = TfidfVectorizer(
            tokenizer=tokenize, lowercase=False, token_pattern=None, ngram_range=(1, 2), sublinear_tf=True
        )
        try:
            self.vectorizer.fit(corpus)
        except ValueError:  # empty corpus / no usable tokens (e.g. no eligible products)
            self.vectorizer = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.vectorizer is None:
            return np.zeros((len(texts), 1), dtype=np.float32)
        return _l2_normalize(self.vectorizer.transform(texts).toarray())

    def encode_corpus(self, texts: list[str]) -> np.ndarray:
        return self.encode(texts)


def create_encoder(corpus: list[str], model_name: str, cache_dir: Optional[Path],
                   force_fallback: bool) -> tuple[Encoder, str, Optional[str]]:
    """Return (encoder, model_status, fallback_reason)."""
    if force_fallback:
        logger.warning("Embedding model disabled by configuration; using TF-IDF fallback.")
        return TfidfEncoder(corpus), "disabled", "forced by REC_FORCE_FALLBACK"
    try:
        encoder = SentenceTransformerEncoder(model_name, cache_dir=cache_dir)
        logger.info("Loaded embedding model %s", model_name)
        return encoder, "loaded", None
    except Exception as exc:  # noqa: BLE001 - any failure must degrade gracefully
        reason = f"{type(exc).__name__}: {exc}"
        logger.error("Could not load embedding model (%s); falling back to TF-IDF.", reason)
        return TfidfEncoder(corpus), "unavailable", reason
