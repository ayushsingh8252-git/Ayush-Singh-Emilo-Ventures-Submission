"""Application settings.

All tunables live here so the ranking behaviour can be adjusted without
touching service code. Values can be overridden with environment variables
(prefix ``REC_``), e.g. ``REC_FORCE_FALLBACK=true``.

The optional LLM layer is configured with unprefixed variables
(``LLM_ENABLED``, ``LLM_PROVIDER``, ``GEMINI_API_KEY``, ``GEMINI_MODEL``,
``LLM_TIMEOUT_SECONDS``), which may also live in a ``.env`` file in the
repository root or in ``backend/``. Real environment variables always win.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(*paths: Path) -> None:
    """Minimal ``KEY=VALUE`` loader; never overrides existing variables."""
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(f"REC_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _raw_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _raw_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class ScoringWeights:
    """Weights of the hybrid score. They are re-normalised per query when a
    component carries no signal (see ``utils.scoring.combine_scores``)."""

    semantic: float = 0.55
    keyword: float = 0.20
    concept: float = 0.25


@dataclass(frozen=True)
class Settings:
    data_path: Path = field(
        default_factory=lambda: Path(_env("DATA_PATH", str(BACKEND_DIR / "data" / "products.json")))
    )
    cache_dir: Path = field(default_factory=lambda: Path(_env("CACHE_DIR", str(BACKEND_DIR / ".cache"))))
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    # Skip the transformer entirely and run the TF-IDF fallback (useful for
    # offline machines and for testing the fallback path).
    force_fallback: bool = field(default_factory=lambda: _env_bool("FORCE_FALLBACK", False))

    weights: ScoringWeights = field(default_factory=ScoringWeights)

    # Results below this final score are treated as "not relevant" and are
    # never shown just to fill the grid.
    min_relevance: float = field(default_factory=lambda: _env_float("MIN_RELEVANCE", 0.30))
    # ...and results must also be within this fraction of the best result.
    relative_cutoff: float = field(default_factory=lambda: _env_float("RELATIVE_CUTOFF", 0.5))

    default_limit: int = 10
    max_limit: int = 24
    candidate_pool: int = 60

    # Products whose title names a different occasion are scaled by
    # 1 - strength * (1 - concept overlap of the two occasions).
    occasion_conflict_strength: float = 0.5
    # Gift add-ons (wrapping, wax seals, gift boxes, greeting cards) are scaled
    # by this factor unless the query asks for them. 1.0 disables it.
    accessory_factor: float = 0.7

    # Diversity re-ranking (MMR-style). Kept small so relevance dominates.
    diversity_lambda: float = 0.06
    same_category_penalty: float = 0.02
    same_group_penalty: float = 0.01

    # --- Optional LLM query understanding -------------------------------
    llm_enabled: bool = field(default_factory=lambda: _raw_bool("LLM_ENABLED", False))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini").strip().lower())
    # repr=False keeps the key out of logs, tracebacks and debug output.
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip(), repr=False)
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip())
    llm_timeout_seconds: float = field(default_factory=lambda: _raw_float("LLM_TIMEOUT_SECONDS", 5.0))
    # USD per 1M tokens, only used to *estimate* cost in reports. Defaults are the
    # paid Standard-tier list prices of gemini-3.1-flash-lite (checked Nov 2026,
    # ai.google.dev/gemini-api/docs/pricing); override them if prices change.
    llm_input_price_per_m: float = field(default_factory=lambda: _raw_float("LLM_INPUT_PRICE_PER_M", 0.25))
    llm_output_price_per_m: float = field(default_factory=lambda: _raw_float("LLM_OUTPUT_PRICE_PER_M", 1.50))

    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        )
    )


settings = Settings()
