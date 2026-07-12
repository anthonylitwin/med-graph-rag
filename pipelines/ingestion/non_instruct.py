from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TERMINOLOGY_PATH = Path("data/terminology/biomedical_aliases_v001.json")


class TextEmbedder(Protocol):
    model: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model: str = DEFAULT_EMBEDDING_MODEL, sentence_transformer: Any | None = None) -> None:
        self.model = model
        self._sentence_transformer = sentence_transformer

    def _load(self) -> Any:
        if self._sentence_transformer is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "Install requirements-local-models.txt to use non-instruct semantic scoring"
                ) from exc
            self._sentence_transformer = SentenceTransformer(self.model)
        return self._sentence_transformer

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._load().encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [vector.tolist() for vector in vectors]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def normalize_term(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("‐", "-").replace("‑", "-").replace("–", "-")
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = re.sub(r"[-_\s]+", " ", normalized)
    return normalized.strip()


@dataclass(frozen=True, slots=True)
class Concept:
    type: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    identifiers: dict[str, str] | None = None

    def search_texts(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.aliases)


@dataclass(frozen=True, slots=True)
class NormalizedMention:
    type: str
    text: str
    canonical_name: str
    start: int
    end: int
    confidence: float
    normalization_method: str
    normalization_score: float
    identifiers: dict[str, str]

    def entity_payload(self) -> dict[str, Any]:
        return {
            "id": "",
            "type": self.type,
            "name": self.canonical_name,
            "properties": {
                "mention_text": self.text,
                "normalized_name": self.canonical_name,
                "ner_confidence": self.confidence,
                "normalization_method": self.normalization_method,
                "normalization_score": self.normalization_score,
                **self.identifiers,
            },
        }


class SemanticConceptIndex:
    def __init__(self, concepts: Sequence[Concept], embedder: TextEmbedder) -> None:
        self.concepts = list(concepts)
        self.embedder = embedder
        self._entries: list[tuple[Concept, str]] = [
            (concept, text)
            for concept in self.concepts
            for text in concept.search_texts()
            if text.strip()
        ]
        self._vectors: list[list[float]] | None = None

    def search(self, query: str, entity_type: str, threshold: float) -> tuple[Concept | None, float]:
        typed_indexes = [
            index for index, (concept, _) in enumerate(self._entries) if concept.type == entity_type
        ]
        if not typed_indexes:
            return None, 0.0
        if self._vectors is None:
            self._vectors = self.embedder.encode([text for _, text in self._entries])
        query_vectors = self.embedder.encode([query])
        if not query_vectors:
            return None, 0.0
        scored = [
            (cosine_similarity(query_vectors[0], self._vectors[index]), self._entries[index][0])
            for index in typed_indexes
        ]
        score, concept = max(scored, key=lambda item: item[0])
        return (concept, score) if score >= threshold else (None, score)


class TerminologyNormalizer:
    def __init__(
        self,
        concepts: Sequence[Concept] = (),
        semantic_index: SemanticConceptIndex | None = None,
        semantic_threshold: float = 0.84,
    ) -> None:
        self.concepts = list(concepts)
        self.semantic_index = semantic_index
        self.semantic_threshold = semantic_threshold
        self._aliases: dict[tuple[str, str], Concept] = {}
        for concept in self.concepts:
            for value in concept.search_texts():
                self._aliases[(concept.type, normalize_term(value))] = concept

    @classmethod
    def from_json(
        cls,
        path: Path | None,
        *,
        embedder: TextEmbedder | None = None,
        semantic_threshold: float = 0.84,
    ) -> "TerminologyNormalizer":
        concepts: list[Concept] = []
        if path is not None and not path.exists():
            raise FileNotFoundError(f"Non-instruct terminology file does not exist: {path}")
        if path is not None:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for raw in payload.get("concepts", []) if isinstance(payload, dict) else []:
                if not isinstance(raw, dict):
                    continue
                entity_type = str(raw.get("type") or "").strip()
                canonical_name = str(raw.get("canonical_name") or "").strip()
                if not entity_type or not canonical_name:
                    continue
                aliases = tuple(str(item).strip() for item in raw.get("aliases", []) if str(item).strip())
                identifiers = {
                    str(key): str(value)
                    for key, value in (raw.get("identifiers") or {}).items()
                    if str(value).strip()
                }
                concepts.append(Concept(entity_type, canonical_name, aliases, identifiers))
        semantic_index = SemanticConceptIndex(concepts, embedder) if embedder is not None and concepts else None
        return cls(concepts, semantic_index, semantic_threshold)

    def normalize(
        self,
        *,
        entity_type: str,
        text: str,
        start: int,
        end: int,
        confidence: float,
    ) -> NormalizedMention:
        exact = self._aliases.get((entity_type, normalize_term(text)))
        if exact is not None:
            return NormalizedMention(
                entity_type,
                text,
                exact.canonical_name,
                start,
                end,
                confidence,
                "alias",
                1.0,
                dict(exact.identifiers or {}),
            )
        if self.semantic_index is not None:
            concept, score = self.semantic_index.search(text, entity_type, self.semantic_threshold)
            if concept is not None:
                return NormalizedMention(
                    entity_type,
                    text,
                    concept.canonical_name,
                    start,
                    end,
                    confidence,
                    "semantic",
                    round(score, 6),
                    dict(concept.identifiers or {}),
                )
        cleaned = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip(" \t\r\n,;:")
        return NormalizedMention(
            entity_type,
            text,
            cleaned,
            start,
            end,
            confidence,
            "surface",
            1.0,
            {},
        )


@dataclass(frozen=True, slots=True)
class RelationshipSpec:
    type: str
    source_types: tuple[str, ...]
    target_types: tuple[str, ...]
    cues: tuple[str, ...]
    prototypes: tuple[str, ...]


RELATIONSHIP_SPECS = (
    RelationshipSpec("TREATS", ("Drug",), ("Condition",), ("treat", "therapy", "improved"), ("A drug treats a medical condition.",)),
    RelationshipSpec("PREVENTS", ("Drug",), ("Condition",), ("prevent", "prophylaxis", "reduced incidence"), ("A drug prevents a disease or clinical event.",)),
    RelationshipSpec("REDUCES", ("Drug",), ("Biomarker",), ("reduce", "lower", "decrease", "decline"), ("A drug lowers a biomarker level.",)),
    RelationshipSpec("INCREASES", ("Drug",), ("Biomarker",), ("increase", "raise", "elevate"), ("A drug raises a biomarker level.",)),
    RelationshipSpec("HAS_ADVERSE_EFFECT", ("Drug",), ("Condition",), ("adverse", "side effect", "toxicity", "induced"), ("A drug causes an adverse clinical effect.",)),
    RelationshipSpec("CAUSES", ("Condition",), ("Condition",), ("cause", "leads to", "results in", "pathogenesis"), ("One medical condition causes another condition.",)),
    RelationshipSpec("HAS_SYMPTOM", ("Condition",), ("Symptom",), ("symptom", "presented with", "characterized by"), ("A medical condition has a symptom.",)),
    RelationshipSpec("INCREASES_RISK_OF", ("RiskFactor",), ("Condition",), ("risk", "increased likelihood", "predispose"), ("A risk factor increases the risk of a medical condition.",)),
    RelationshipSpec("INTERACTS_WITH", ("Drug",), ("Drug",), ("interact", "coadministration", "combination"), ("Two drugs interact clinically.",)),
    RelationshipSpec("CONTRAINDICATED_FOR", ("Drug",), ("Condition",), ("contraindicat", "should not be used", "avoid"), ("A drug is contraindicated for a condition.",)),
    RelationshipSpec("ASSOCIATED_WITH", ("Drug", "Condition", "Symptom", "RiskFactor", "Biomarker"), ("Drug", "Condition", "Symptom", "RiskFactor", "Biomarker"), ("associated", "correlated", "linked", "marker", "prevalence"), ("Two biomedical entities are clinically or statistically associated.",)),
)


@dataclass(frozen=True, slots=True)
class RelationScoringConfig:
    relation_threshold: float = 0.66
    semantic_floor: float = 0.52
    semantic_weight: float = 0.50
    cue_weight: float = 0.25
    proximity_weight: float = 0.10
    entity_confidence_weight: float = 0.15
    max_pair_distance: int = 300

    def __post_init__(self) -> None:
        for name in ("relation_threshold", "semantic_floor"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        weights = (
            self.semantic_weight,
            self.cue_weight,
            self.proximity_weight,
            self.entity_confidence_weight,
        )
        if any(value < 0 for value in weights) or sum(weights) <= 0:
            raise ValueError("Relation score weights must be non-negative and sum to more than zero")
        if self.max_pair_distance <= 0:
            raise ValueError("max_pair_distance must be positive")


@dataclass(frozen=True, slots=True)
class NonInstructPipelineConfig:
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    terminology_path: Path | None = DEFAULT_TERMINOLOGY_PATH
    entity_threshold: float = 0.5
    concept_threshold: float = 0.84
    relation_scoring: RelationScoringConfig = RelationScoringConfig()

    def __post_init__(self) -> None:
        if not self.embedding_model.strip():
            raise ValueError("embedding_model is required")
        for name in ("entity_threshold", "concept_threshold"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class RelationCandidate:
    relationship_type: str
    source: NormalizedMention
    target: NormalizedMention
    evidence: str
    semantic_score: float
    cue_score: float
    proximity_score: float
    entity_confidence_score: float
    confidence: float
    accepted: bool
    rejection_reason: str = ""

    def audit_payload(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "source": asdict(self.source),
            "target": asdict(self.target),
            "evidence": self.evidence,
            "semantic_score": self.semantic_score,
            "cue_score": self.cue_score,
            "proximity_score": self.proximity_score,
            "entity_confidence_score": self.entity_confidence_score,
            "confidence": self.confidence,
            "accepted": self.accepted,
            "rejection_reason": self.rejection_reason,
        }


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+|\n+", text):
        end = match.start()
        sentence = text[start:end].strip()
        if sentence:
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            spans.append((start + leading, end, sentence))
        start = match.end()
    sentence = text[start:].strip()
    if sentence:
        leading = len(text[start:]) - len(text[start:].lstrip())
        spans.append((start + leading, len(text), sentence))
    return spans


class RelationCandidateScorer:
    NEGATION_PATTERN = re.compile(r"\b(no|not|without|neither|failed to|did not|wasn't|were not)\b", re.IGNORECASE)

    def __init__(
        self,
        embedder: TextEmbedder,
        config: RelationScoringConfig = RelationScoringConfig(),
        specs: Sequence[RelationshipSpec] = RELATIONSHIP_SPECS,
    ) -> None:
        self.embedder = embedder
        self.config = config
        self.specs = list(specs)
        self._prototype_vectors: dict[str, list[list[float]]] | None = None

    def _load_prototypes(self) -> dict[str, list[list[float]]]:
        if self._prototype_vectors is None:
            texts = [prototype for spec in self.specs for prototype in spec.prototypes]
            vectors = iter(self.embedder.encode(texts))
            self._prototype_vectors = {
                spec.type: [next(vectors) for _ in spec.prototypes] for spec in self.specs
            }
        return self._prototype_vectors

    def score(self, text: str, mentions: Sequence[NormalizedMention]) -> list[RelationCandidate]:
        if len(mentions) < 2:
            return []
        prototypes = self._load_prototypes()
        candidates: list[RelationCandidate] = []
        for sentence_start, sentence_end, sentence in _sentence_spans(text):
            sentence_mentions = [
                mention
                for mention in mentions
                if mention.start < sentence_end and mention.end > sentence_start
            ]
            if len(sentence_mentions) < 2:
                continue
            sentence_vectors = self.embedder.encode([sentence])
            sentence_vector = sentence_vectors[0] if sentence_vectors else []
            negated = bool(self.NEGATION_PATTERN.search(sentence))
            for spec in self.specs:
                for source in sentence_mentions:
                    if source.type not in spec.source_types:
                        continue
                    for target in sentence_mentions:
                        if target is source or target.type not in spec.target_types:
                            continue
                        if spec.type == "ASSOCIATED_WITH" and source.start > target.start:
                            continue
                        if source.canonical_name == target.canonical_name and source.type == target.type:
                            continue
                        distance = max(0, max(source.start, target.start) - min(source.end, target.end))
                        if distance > self.config.max_pair_distance:
                            continue
                        semantic = max(
                            (cosine_similarity(sentence_vector, vector) for vector in prototypes[spec.type]),
                            default=0.0,
                        )
                        semantic = max(0.0, semantic)
                        normalized_sentence = normalize_term(sentence)
                        cue = 1.0 if any(normalize_term(item) in normalized_sentence for item in spec.cues) else 0.0
                        proximity = max(0.0, 1.0 - distance / max(1, self.config.max_pair_distance))
                        entity_confidence = (source.confidence + target.confidence) / 2
                        total_weight = (
                            self.config.semantic_weight
                            + self.config.cue_weight
                            + self.config.proximity_weight
                            + self.config.entity_confidence_weight
                        ) or 1.0
                        score = (
                            semantic * self.config.semantic_weight
                            + cue * self.config.cue_weight
                            + proximity * self.config.proximity_weight
                            + entity_confidence * self.config.entity_confidence_weight
                        ) / total_weight
                        reason = ""
                        accepted = score >= self.config.relation_threshold
                        if cue == 0 and semantic < self.config.semantic_floor:
                            accepted = False
                            reason = "semantic score below floor and no lexical cue matched"
                        if negated:
                            accepted = False
                            reason = "sentence contains a negation cue"
                        candidates.append(
                            RelationCandidate(
                                spec.type,
                                source,
                                target,
                                sentence,
                                round(semantic, 6),
                                cue,
                                round(proximity, 6),
                                round(entity_confidence, 6),
                                round(score, 6),
                                accepted,
                                reason or ("score below relation threshold" if not accepted else ""),
                            )
                        )
        return candidates


def accepted_relationships(candidates: Sequence[RelationCandidate]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str, str, str, str], RelationCandidate] = {}
    for candidate in candidates:
        if not candidate.accepted:
            continue
        key = (
            candidate.relationship_type,
            candidate.source.type,
            candidate.source.canonical_name,
            candidate.target.type,
            candidate.target.canonical_name,
        )
        current = best.get(key)
        if current is None or candidate.confidence > current.confidence:
            best[key] = candidate
    return [
        {
            "type": candidate.relationship_type,
            "source": {
                "type": candidate.source.type,
                "name": candidate.source.canonical_name,
            },
            "target": {
                "type": candidate.target.type,
                "name": candidate.target.canonical_name,
            },
            "properties": {
                "confidence": candidate.confidence,
                "evidence": candidate.evidence,
                "semantic_score": candidate.semantic_score,
                "cue_score": candidate.cue_score,
                "proximity_score": candidate.proximity_score,
                "entity_confidence_score": candidate.entity_confidence_score,
            },
        }
        for candidate in best.values()
    ]


__all__ = [
    "Concept",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_TERMINOLOGY_PATH",
    "NormalizedMention",
    "NonInstructPipelineConfig",
    "RelationCandidate",
    "RelationCandidateScorer",
    "RelationScoringConfig",
    "SemanticConceptIndex",
    "SentenceTransformerEmbedder",
    "TerminologyNormalizer",
    "TextEmbedder",
    "accepted_relationships",
    "cosine_similarity",
    "normalize_term",
]
