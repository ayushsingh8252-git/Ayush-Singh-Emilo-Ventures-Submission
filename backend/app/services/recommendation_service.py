"""Hybrid occasion-based recommendation engine.

Pipeline per request
--------------------
1. Occasion understanding  -> concepts, keyword terms, budget, expansion text
2. Query embedding         -> blend of the raw query and the occasion expansion
3. Candidate retrieval     -> FAISS top-K (restricted to filtered IDs) ∪ keyword hits
4. Hybrid scoring          -> semantic + keyword + concept, each in [0, 1]
5. Relevance cut-off       -> absolute floor + fraction of the best score
6. Diversity re-ranking    -> MMR with category / product-group penalties
7. Explanation             -> built only from matched concepts, matched terms
                              and a quoted sentence of the product's description

Everything expensive (catalog normalisation, product + sentence embeddings,
the FAISS index, IDF tables) is built once in ``build``.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.config import Settings
from app.models.product import (
    OccasionInterpretation,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    ScoreBreakdown,
)
from app.services.data_loader import CatalogLoadResult, load_catalog
from app.services.embedding_service import MODE_SEMANTIC, Encoder, create_encoder
from app.services.occasion_service import CONCEPTS, OccasionIntent, OccasionService
from app.services.llm.providers import create_provider
from app.services.query_understanding import QueryUnderstandingService
from app.services.preprocessing import (
    ProductDocument,
    build_documents,
    fold,
    infer_category_labels,
    stem,
    tokenize,
)
from app.services.vector_store import VectorStore, create_vector_store
from app.utils.scoring import (
    calibrate_similarity,
    combine_scores,
    compute_idf,
    concept_relevance,
    keyword_relevance,
)

logger = logging.getLogger(__name__)

GENERIC_GIFT_QUERY = "a thoughtful, well-loved gift for someone special"
EMPTY_MESSAGE = "No relevant products found for this occasion. Try another occasion."
QUERY_WEIGHT_WITH_PROFILE = 0.4  # raw-query share of the blended query embedding
BOILERPLATE_EMBEDDING_WEIGHT = 0.3  # share of shared vendor text in a product vector
# (title, description, boilerplate) field weights for the two lexical signals
KEYWORD_FIELD_WEIGHTS = (1.0, 0.6, 0.25)
CONCEPT_FIELD_WEIGHTS = (1.0, 0.7, 0.35)
# Generic gifting words that carry no occasion signal; stripped before the raw
# query is embedded so "gift for a child" is not pulled towards "Gift Boxes".
FILLER_WORDS = frozenset("gift gifts present presents something anything idea ideas for a an my the some".split())
# Gift add-ons: packaging/cards that accompany a gift rather than being one.
# Matched against the title; demoted unless the query mentions them.
ACCESSORY_TITLE_TERMS = frozenset({"wrapping", "wrap", "seal", "sticker", "ribbon", "greeting", "gretting"})
ACCESSORY_TITLE_PHRASES = ("gift box",)
ACCESSORY_QUERY_TERMS = frozenset({"wrapping", "wrap", "box", "seal", "sticker", "ribbon", "greeting", "card",
                                   "packaging", "accessory"})


@dataclass
class _Scored:
    index: int
    final: float
    semantic: float
    keyword: float
    concept: float
    keyword_terms: list[str]
    concepts: dict[str, list[str]]
    non_keyword: float = 0.0  # semantic + concept only, used by the relevance gate


class RecommendationEngine:
    def __init__(self, settings: Settings, catalog: CatalogLoadResult, docs: list[ProductDocument],
                 encoder: Encoder, vectors: np.ndarray, store: VectorStore, occasions: OccasionService,
                 model_status: str, fallback_reason: Optional[str], vector_fallback_reason: Optional[str],
                 understanding: Optional[QueryUnderstandingService] = None) -> None:
        self.settings = settings
        self.catalog = catalog
        self.docs = docs
        self.encoder = encoder
        self.vectors = vectors
        self.store = store
        self.occasions = occasions
        self.model_status = model_status
        self.fallback_reason = fallback_reason
        self.vector_fallback_reason = vector_fallback_reason
        # Optional LLM layer; without it the existing rule-based service is used.
        self.understanding = understanding or QueryUnderstandingService(occasions)
        self.idf = compute_idf(d.body_tokens | d.shared_tokens for d in docs)
        self.concept_keywords = {k: c.keywords for k, c in CONCEPTS.items()}
        self.category_labels = infer_category_labels([d.product for d in docs])
        # Occasions explicitly named in each product title (e.g. "Diwali ... hampers").
        self._title_occasions = [
            [p for p in occasions.match_aliases(d.product.title) if p.is_occasion] for d in docs
        ]
        self._is_accessory = [
            bool(ACCESSORY_TITLE_TERMS & d.title_tokens)
            or any(p in " ".join(tokenize(d.product.title, drop_stopwords=False)) for p in ACCESSORY_TITLE_PHRASES)
            for d in docs
        ]
        self._index_sentences()

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, settings: Settings, catalog: Optional[CatalogLoadResult] = None) -> "RecommendationEngine":
        started = time.perf_counter()
        catalog = catalog if catalog is not None else load_catalog(settings.data_path)
        docs = build_documents(catalog.eligible)
        encoder, model_status, fallback_reason = create_encoder(
            [f"{d.embedding_text} {d.shared_text}" for d in docs],
            settings.embedding_model, settings.cache_dir, settings.force_fallback,
        )
        vectors = cls._embed_documents(encoder, docs) if docs else np.zeros((0, 1), dtype=np.float32)
        store, vector_fallback_reason = create_vector_store(vectors)
        occasions = OccasionService(encode=encoder.encode if encoder.mode == MODE_SEMANTIC else None)
        provider, llm_status, llm_reason = create_provider(settings)
        understanding = QueryUnderstandingService(occasions, provider, llm_status, llm_reason)
        engine = cls(settings, catalog, docs, encoder, vectors, store, occasions,
                     model_status, fallback_reason, vector_fallback_reason, understanding)
        logger.info(
            "Recommendation engine ready in %.1fs: mode=%s, vector_store=%s, indexed=%d",
            time.perf_counter() - started, encoder.mode, store.backend, store.size,
        )
        return engine

    @staticmethod
    def _embed_documents(encoder: Encoder, docs: list[ProductDocument]) -> np.ndarray:
        """Product vector = specific text + down-weighted boilerplate, re-normalised."""
        vectors = encoder.encode_corpus([d.embedding_text for d in docs])
        shared_rows = [i for i, d in enumerate(docs) if d.shared_text]
        if shared_rows:
            shared = encoder.encode_corpus([docs[i].shared_text for i in shared_rows])
            vectors[shared_rows] += BOILERPLATE_EMBEDDING_WEIGHT * shared
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True).clip(min=1e-12)
        return vectors.astype(np.float32)

    @staticmethod
    def _fields(doc: ProductDocument, weights: tuple[float, float, float]) -> list:
        return [(doc.title_tokens, weights[0]), (doc.body_tokens, weights[1]), (doc.shared_tokens, weights[2])]

    def _index_sentences(self) -> None:
        """Embed description sentences once so explanations can quote evidence."""
        owners, sentences = [], []
        for i, doc in enumerate(self.docs):
            for sentence in doc.sentences:
                owners.append(i)
                sentences.append(sentence)
        self._sentence_owner = np.array(owners, dtype=np.int64)
        self._sentences = sentences
        self._sentence_vectors = (
            self.encoder.encode(sentences) if sentences else np.zeros((0, 1), dtype=np.float32)
        )

    # ------------------------------------------------------------ public API
    @property
    def mode(self) -> str:
        return self.encoder.mode

    def health(self) -> dict:
        return {
            "status": "ok",
            "total_products_loaded": self.catalog.total_records,
            "valid_products": len(self.catalog.products),
            "eligible_products": len(self.catalog.eligible),
            "indexed_products": self.store.size,
            "rejected_products": dict(self.catalog.rejected),
            "recommendation_mode": self.encoder.mode,
            "embedding_model": self.settings.embedding_model,
            "embedding_model_status": self.model_status,
            "fallback_reason": self.fallback_reason,
            "vector_store": self.store.backend,
            "vector_store_fallback_reason": self.vector_fallback_reason,
            "llm": {
                "enabled": self.settings.llm_enabled,
                "status": self.understanding.status,  # ready | disabled | missing_key | unsupported_provider
                "provider": self.understanding.provider.name if self.understanding.provider else None,
                "model": self.understanding.provider.model if self.understanding.provider else None,
                "detail": self.understanding.status_reason,
            },
        }

    def categories(self) -> list[dict]:
        counts: dict[str, int] = {}
        for doc in self.docs:
            counts[doc.product.category_id] = counts.get(doc.product.category_id, 0) + 1
        return sorted(
            (
                {"category_id": cid, "label": self.category_labels.get(cid, cid), "label_is_inferred": True,
                 "product_count": n}
                for cid, n in counts.items()
            ),
            key=lambda c: c["label"],
        )

    def recommend(self, request: RecommendRequest) -> RecommendResponse:
        understood = self.understanding.understand(request.text, request.use_llm)
        intent = understood.intent
        min_price = request.min_price if request.min_price is not None else intent.min_price
        max_price = request.max_price if request.max_price is not None else intent.max_price
        interpretation = OccasionInterpretation(
            matched_occasion=intent.display_name,
            match_type=intent.match_type,
            concepts=[c.phrase for c in intent.concepts],
            applied_min_price=min_price,
            applied_max_price=max_price,
            recipient=understood.recipient,
            preferences=understood.preferences,
            understanding_mode=understood.mode,
            llm_provider=understood.provider,
            llm_model=understood.model,
            llm_fallback_reason=understood.fallback_reason,
            understanding_latency_ms=round(understood.latency_ms, 1),
            understanding_route=understood.route,
        )

        def response(items: list[Recommendation], message: Optional[str] = None) -> RecommendResponse:
            return RecommendResponse(
                occasion=request.text, interpretation=interpretation, total_results=len(items),
                recommendation_mode=self.mode, recommendations=items, message=message,
            )

        if not self.docs:
            return response([], "No eligible products are available in the catalog right now.")
        allowed = self._filter(min_price, max_price, request.category)
        if not allowed:
            return response([], "No products match the selected filters. Try widening the price range or category.")

        query_vector = self._query_vector(intent)
        scored = self._score_candidates(intent, query_vector, allowed)
        relevant = self._apply_relevance_cutoff(scored, generic=intent.match_type == "generic")
        if not relevant:
            return response([], EMPTY_MESSAGE)

        ranked = self._diversify(relevant, request.limit)
        items = [self._to_recommendation(s, intent, query_vector) for s in ranked]
        return response(items)

    # -------------------------------------------------------------- stages
    def _filter(self, min_price: Optional[float], max_price: Optional[float], category: Optional[str]) -> set[int]:
        allowed = set()
        for i, doc in enumerate(self.docs):
            p = doc.product
            if category and p.category_id != category:
                continue
            price = p.final_price
            if (min_price is not None or max_price is not None) and price is None:
                continue
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue
            allowed.add(i)
        return allowed

    def _query_vector(self, intent: OccasionIntent) -> np.ndarray:
        if intent.match_type == "generic":
            return self.encoder.encode([GENERIC_GIFT_QUERY])[0]
        words = intent.search_text.split()
        raw_text = " ".join(w for w in words if w.lower() not in FILLER_WORDS) or intent.search_text
        if not intent.expansion_text:
            return self.encoder.encode([raw_text])[0]
        raw, expansion = self.encoder.encode([raw_text, intent.expansion_text])
        blended = QUERY_WEIGHT_WITH_PROFILE * raw + (1 - QUERY_WEIGHT_WITH_PROFILE) * expansion
        norm = np.linalg.norm(blended)
        return (blended / norm).astype(np.float32) if norm else expansion

    def _score_candidates(self, intent: OccasionIntent, query_vector: np.ndarray, allowed: set[int]) -> list[_Scored]:
        k = min(self.settings.candidate_pool, len(allowed))
        semantic_hits = dict(self.store.search(query_vector, k, allowed))

        keyword_hits: dict[int, tuple[float, list[str]]] = {}
        for i in allowed:
            doc = self.docs[i]
            score, terms = keyword_relevance(intent.keyword_terms, self._fields(doc, KEYWORD_FIELD_WEIGHTS), self.idf)
            if score > 0:
                keyword_hits[i] = (score, terms)

        candidates = set(semantic_hits) | set(keyword_hits)
        # Keyword-only candidates still need their true cosine similarity.
        missing = [i for i in candidates if i not in semantic_hits]
        if missing:
            sims = self.vectors[missing] @ query_vector
            semantic_hits.update({i: float(s) for i, s in zip(missing, sims)})

        partial = []
        for i in candidates:
            doc = self.docs[i]
            concept, matched = concept_relevance(
                intent.concept_weights, self.concept_keywords, self._fields(doc, CONCEPT_FIELD_WEIGHTS)
            )
            kw_score, kw_terms = keyword_hits.get(i, (0.0, []))
            semantic = calibrate_similarity(
                semantic_hits[i], self.encoder.semantic_floor, self.encoder.semantic_ceil
            )
            partial.append((i, semantic, kw_score, kw_terms, concept, matched))

        keyword_informative = any(p[2] > 0 for p in partial)
        concept_informative = any(p[4] > 0 for p in partial)
        weights = self.settings.weights
        scored = []
        for i, semantic, kw_score, kw_terms, concept, matched in partial:
            factor = self._occasion_conflict_factor(intent, i) * self._accessory_factor(intent, i)
            final = factor * combine_scores(semantic, kw_score, concept, weights,
                                            keyword_informative, concept_informative)
            non_keyword = factor * combine_scores(semantic, 0.0, concept, weights, False, concept_informative)
            scored.append(_Scored(i, final, semantic, kw_score, concept, kw_terms, matched, non_keyword))
        scored.sort(key=lambda s: s.final, reverse=True)
        return scored

    def _occasion_conflict_factor(self, intent: OccasionIntent, index: int) -> float:
        named = self._title_occasions[index]
        if not named or not intent.matched_profiles or any(p in intent.matched_profiles for p in named):
            return 1.0
        product_weights: dict[str, float] = {}
        for profile in named:
            for key, weight in profile.concepts.items():
                product_weights[key] = max(product_weights.get(key, 0.0), weight)
        keys = set(product_weights) | set(intent.concept_weights)
        overlap = sum(min(product_weights.get(k, 0), intent.concept_weights.get(k, 0)) for k in keys)
        union = sum(max(product_weights.get(k, 0), intent.concept_weights.get(k, 0)) for k in keys)
        jaccard = overlap / union if union else 0.0
        return 1.0 - self.settings.occasion_conflict_strength * (1.0 - jaccard)

    def _accessory_factor(self, intent: OccasionIntent, index: int) -> float:
        """Demote gift add-ons for occasion queries unless the user asked for them.

        A wax seal or gift box complements a present; ranking it as the present
        for "Graduation" is a relevance error even when its text is gift-heavy.
        """
        if not self._is_accessory[index] or ACCESSORY_QUERY_TERMS & set(intent.keyword_terms):
            return 1.0
        return self.settings.accessory_factor

    def _apply_relevance_cutoff(self, scored: list[_Scored], generic: bool) -> list[_Scored]:
        """Keep products that clear an absolute floor *and* are close to the best.

        "Close to the best" is judged on the full hybrid score or on the
        semantic+concept score alone, so a single product that literally
        repeats the query word ("Diwali ... hampers") cannot push every other
        thematically strong product below the cut.
        """
        if not scored:
            return []
        if generic:  # budget-only queries: everything in budget is fair game
            return scored
        s = self.settings
        best_final = max(x.final for x in scored)
        best_non_keyword = max(x.non_keyword for x in scored) or 1.0
        return [
            x for x in scored
            if x.final >= s.min_relevance
            and max(x.final / best_final, x.non_keyword / best_non_keyword) >= s.relative_cutoff
        ]

    def _diversify(self, scored: list[_Scored], limit: int) -> list[_Scored]:
        """Greedy MMR: relevance minus redundancy with already-selected items.

        Redundancy = embedding similarity to the closest selected product plus
        small penalties for repeating a category or product group. Penalties
        are small relative to relevance gaps, so diversity never promotes a
        clearly weaker product over a much stronger one.
        """
        s = self.settings
        pool, selected = list(scored), []
        while pool and len(selected) < limit:
            best_item, best_value = None, -np.inf
            for item in pool:
                product = self.docs[item.index].product
                redundancy = 0.0
                if selected:
                    sims = self.vectors[[x.index for x in selected]] @ self.vectors[item.index]
                    redundancy = s.diversity_lambda * float(np.max(sims))
                    redundancy += s.same_category_penalty * sum(
                        self.docs[x.index].product.category_id == product.category_id for x in selected
                    )
                    redundancy += s.same_group_penalty * sum(
                        self.docs[x.index].product.product_group_id == product.product_group_id for x in selected
                    )
                value = item.final - redundancy
                if value > best_value:
                    best_item, best_value = item, value
            selected.append(best_item)
            pool.remove(best_item)
        return selected

    # ---------------------------------------------------------- explanation
    def _evidence_sentence(self, index: int, query_vector: np.ndarray) -> Optional[str]:
        rows = np.where(self._sentence_owner == index)[0]
        if len(rows) == 0:
            return None
        sims = self._sentence_vectors[rows] @ query_vector
        sentence = self._sentences[int(rows[int(np.argmax(sims))])]
        return sentence if len(sentence) <= 140 else sentence[:137].rsplit(" ", 1)[0] + "…"

    @staticmethod
    def _surface_forms(doc: ProductDocument, stems: list[str], limit: int = 3) -> list[str]:
        """Map stemmed terms back to the words actually used in the listing."""
        text = fold(f"{doc.product.title} {doc.product.short_description} {doc.product.description}")
        words = re.findall(r"[a-z0-9]+", text)
        found = []
        for target in stems:
            word = next((w for w in words if stem(w) == target), None)
            if word and word not in found:
                found.append(word)
            if len(found) == limit:
                break
        return found

    @staticmethod
    def _concept_contribution(intent: OccasionIntent, doc: ProductDocument, key: str) -> float:
        """Occasion weight x strongest field weight, mirroring concept_relevance."""
        keywords = CONCEPTS[key].keywords
        field_weight = max(
            (w for tokens, w in zip((doc.title_tokens, doc.body_tokens, doc.shared_tokens), CONCEPT_FIELD_WEIGHTS)
             if any(k in tokens for k in keywords)),
            default=0.0,
        )
        return intent.concept_weights.get(key, 0.0) * field_weight

    def _reason(self, item: _Scored, intent: OccasionIntent, query_vector: np.ndarray) -> str:
        doc = self.docs[item.index]
        if intent.match_type == "generic":
            target = "your budget"
        elif intent.display_name:
            target = intent.display_name
        else:
            target = f"“{intent.search_text}”"

        parts = []
        if item.concepts:
            ordered = sorted(item.concepts, key=lambda k: self._concept_contribution(intent, doc, k),
                             reverse=True)[:2]
            phrases = " and ".join(CONCEPTS[k].phrase for k in ordered)
            terms = self._surface_forms(doc, [t for k in ordered for t in item.concepts[k]])
            mention = f" — the listing mentions {', '.join(f'“{t}”' for t in terms)}" if terms else ""
            parts.append(f"Recommended for {target} because it fits the theme of {phrases}{mention}.")
        elif item.keyword_terms:
            terms = self._surface_forms(doc, item.keyword_terms)
            parts.append(f"Recommended for {target}: the listing directly mentions "
                         f"{', '.join(f'“{t}”' for t in terms)}.")
        else:
            parts.append(f"Recommended for {target} because its description is semantically close to the occasion.")

        if item.keyword_terms and item.concepts:
            extra = [t for t in self._surface_forms(doc, item.keyword_terms) if t not in parts[0]]
            if extra:
                parts.append(f"It also directly mentions {', '.join(f'“{t}”' for t in extra)}.")

        evidence = self._evidence_sentence(item.index, query_vector)
        if evidence and item.semantic >= 0.3:
            parts.append(f"“{evidence}”")
        return " ".join(parts)

    def _to_recommendation(self, item: _Scored, intent: OccasionIntent, query_vector: np.ndarray) -> Recommendation:
        p = self.docs[item.index].product
        return Recommendation(
            product_id=p.product_id,
            name=p.title,
            description=p.description,
            short_description=p.short_description,
            brand=p.brand,
            category_id=p.category_id,
            category_label=p.category_label,
            image_url=p.image_url,
            price=p.price,
            final_price=p.final_price,
            discount_percentage=p.discount_percentage,
            stock=p.stock,
            similarity_score=round(item.final, 4),
            score_breakdown=ScoreBreakdown(
                semantic=round(item.semantic, 4), keyword=round(item.keyword, 4), concept=round(item.concept, 4)
            ),
            matched_concepts=[CONCEPTS[k].phrase for k in item.concepts],
            reason=self._reason(item, intent, query_vector),
        )
