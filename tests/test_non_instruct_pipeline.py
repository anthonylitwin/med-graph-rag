from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from pipelines.ingestion.extractors import NonInstructExtractor
from pipelines.ingestion.models import ChunkRecord
from pipelines.ingestion.models import ExtractionContext
from pipelines.ingestion.non_instruct import (
    Concept,
    NonInstructPipelineConfig,
    NormalizedMention,
    RelationCandidateScorer,
    RelationScoringConfig,
    SemanticConceptIndex,
    TerminologyNormalizer,
    accepted_relationships,
    cosine_similarity,
)
from pipelines.ingestion.validation import validate_extraction_output


class LookupEmbedder:
    model = "lookup-embedding-v0"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            normalized = text.casefold()
            if "lower" in normalized or "reduc" in normalized:
                vectors.append([1.0, 0.0, 0.0])
            elif "heart attack" in normalized or "myocardial infarction" in normalized:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class NonInstructComponentTests(unittest.TestCase):
    def test_threshold_config_rejects_invalid_ranges_and_weights(self) -> None:
        with self.assertRaisesRegex(ValueError, "entity_threshold"):
            NonInstructPipelineConfig(entity_threshold=1.1)
        with self.assertRaisesRegex(ValueError, "relation_threshold"):
            RelationScoringConfig(relation_threshold=-0.1)
        with self.assertRaisesRegex(ValueError, "weights"):
            RelationScoringConfig(
                semantic_weight=0,
                cue_weight=0,
                proximity_weight=0,
                entity_confidence_weight=0,
            )

    def test_cosine_similarity_handles_orthogonal_and_identical_vectors(self) -> None:
        self.assertEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 2.0], [1.0, 2.0]), 1.0)

    def test_normalizer_prefers_exact_alias_then_type_constrained_semantic_match(self) -> None:
        concepts = [
            Concept("Condition", "Myocardial infarction", ("MI",)),
            Concept("Biomarker", "Myocardial injury marker", ("cardiac marker",)),
        ]
        embedder = LookupEmbedder()
        normalizer = TerminologyNormalizer(
            concepts,
            SemanticConceptIndex(concepts, embedder),
            semantic_threshold=0.8,
        )

        exact = normalizer.normalize(
            entity_type="Condition", text="MI", start=0, end=2, confidence=0.9
        )
        semantic = normalizer.normalize(
            entity_type="Condition", text="heart attack", start=3, end=15, confidence=0.8
        )

        self.assertEqual(exact.canonical_name, "Myocardial infarction")
        self.assertEqual(exact.normalization_method, "alias")
        self.assertEqual(semantic.canonical_name, "Myocardial infarction")
        self.assertEqual(semantic.normalization_method, "semantic")

    def test_relation_scorer_accepts_typed_reduction_and_rejects_negation(self) -> None:
        config = RelationScoringConfig(relation_threshold=0.6, semantic_floor=0.4)
        scorer = RelationCandidateScorer(LookupEmbedder(), config)
        mentions = [
            NormalizedMention("Drug", "Fish oil", "Omega-3 fatty acids", 0, 8, 0.9, "alias", 1.0, {}),
            NormalizedMention("Biomarker", "triglycerides", "Triglycerides", 17, 30, 0.9, "surface", 1.0, {}),
        ]

        positive = scorer.score("Fish oil reduced triglycerides.", mentions)
        negative = scorer.score("Fish oil did not reduce triglycerides.", mentions)
        relationships = accepted_relationships(positive)

        self.assertEqual([item["type"] for item in relationships], ["REDUCES"])
        self.assertFalse(any(candidate.accepted for candidate in negative))
        self.assertTrue(any("negation" in candidate.rejection_reason for candidate in negative))

    def test_composed_extractor_writes_normalized_entities_relationships_and_audit(self) -> None:
        class FakeGLiNER:
            def predict_entities(self, text: str, labels: list[str], threshold: float) -> list[dict[str, object]]:
                return [
                    {"text": "Fish oil", "label": "Drug", "score": 0.92, "start": 0, "end": 8},
                    {"text": "triglycerides", "label": "Biomarker", "score": 0.88, "start": 17, "end": 30},
                ]

        concepts = [
            Concept("Drug", "Omega-3 fatty acids", ("Fish oil",)),
            Concept("Biomarker", "Triglycerides", ("triglycerides",)),
        ]
        normalizer = TerminologyNormalizer(concepts)
        scorer = RelationCandidateScorer(
            LookupEmbedder(),
            RelationScoringConfig(relation_threshold=0.6, semantic_floor=0.4),
        )
        chunk = ChunkRecord(
            id="PMC1-chunk-0001",
            document_id="paper:PMC1",
            pmcid="PMC1",
            order=1,
            char_start=0,
            char_end=31,
            section="Abstract",
            type="abstract",
            source_sections=["Abstract"],
            text="Fish oil reduced triglycerides.",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            extractor = NonInstructExtractor(
                entity_model="fake-gliner",
                entity_threshold=0.5,
                pipeline_config=NonInstructPipelineConfig(embedding_model="lookup-embedding-v0"),
                embedder=LookupEmbedder(),
                normalizer=normalizer,
                relation_scorer=scorer,
                gliner_model=FakeGLiNER(),
                model_call_root=Path(temp_dir) / "model_calls",
            )
            output = extractor.extract({"id": "paper:PMC1", "pmcid": "PMC1", "title": "Test"}, chunk)
            normalized = validate_extraction_output(
                output,
                {"id": "paper:PMC1", "pmcid": "PMC1", "title": "Test"},
                chunk,
                ExtractionContext(
                    extractor=extractor.provider,
                    model=extractor.model,
                    min_confidence=0.5,
                    created_at="2026-01-01T00:00:00+00:00",
                ),
            )
            audits = [json.loads(Path(path).read_text(encoding="utf-8")) for path in extractor.last_model_call_paths]

        self.assertEqual([item["name"] for item in output["entities"]], ["Omega-3 fatty acids", "Triglycerides"])
        self.assertEqual([item["type"] for item in output["relationships"]], ["REDUCES"])
        self.assertEqual(normalized["entities"][0]["properties"]["normalization_method"], "alias")
        self.assertEqual(normalized["relationships"][0]["properties"]["semantic_score"], 1.0)
        self.assertEqual(len(audits), 2)
        self.assertEqual(audits[1]["provider"], "non_instruct")
        self.assertTrue(audits[1]["raw_response"]["relation_candidates"])


if __name__ == "__main__":
    unittest.main()
