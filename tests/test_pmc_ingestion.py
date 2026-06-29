from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from pipelines.ingestion.chunking import chunk_article
from pipelines.ingestion.extractors import GLiNEROllamaExtractor, OpenAIResponsesExtractor
from pipelines.ingestion.models import ChunkRecord, ExtractionContext
from pipelines.ingestion.neo4j_loader import load_processed_record_with_session
from pipelines.ingestion.pmc_bioc import parse_bioc_payload
from pipelines.ingestion.pmc_inputs import collect_pmcids, normalize_pmcid, read_pmcid_file
from pipelines.ingestion.validation import validate_extraction_output


class PmcInputTests(unittest.TestCase):
    def test_normalize_pmcid_accepts_prefixed_and_bare_ids(self) -> None:
        self.assertEqual(normalize_pmcid("pmc3572442"), "PMC3572442")
        self.assertEqual(normalize_pmcid("3572442"), "PMC3572442")

    def test_collect_pmcids_dedupes_args_and_newline_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pmcid_file = Path(tmpdir) / "pmcids.txt"
            pmcid_file.write_text("# seed set\nPMC3234107\n\n4866746\n", encoding="utf-8")

            pmcids = collect_pmcids(
                [["PMC3572442", "PMC3234107"], ["3572442"]],
                pmcid_file,
                limit=None,
            )

        self.assertEqual(pmcids, ["PMC3572442", "PMC3234107", "PMC4866746"])

    def test_pmcid_file_rejects_mixed_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pmcid_file = Path(tmpdir) / "pmcids.txt"
            pmcid_file.write_text("| title | PMC3572442 |\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                read_pmcid_file(pmcid_file)


class BioCParsingAndChunkingTests(unittest.TestCase):
    def test_parse_bioc_payload_accepts_list_shaped_response(self) -> None:
        payload = [
            {
                "documents": [
                    {
                        "infons": {
                            "article-id_pmid": "12345",
                            "article-title": "Fish oil and triglycerides",
                            "journal": "Example Journal",
                            "year": "2024",
                        },
                        "passages": [
                            {"infons": {"type": "title"}, "offset": 0, "text": "Fish oil and triglycerides"},
                            {
                                "infons": {"section": "Abstract", "type": "abstract"},
                                "offset": 32,
                                "text": "Fish oil reduced triglycerides in adults.",
                            },
                        ],
                    }
                ]
            }
        ]

        article = parse_bioc_payload(payload, "3572442")

        self.assertEqual(article.document["id"], "paper:PMC3572442")
        self.assertEqual(article.document["pmid"], "12345")
        self.assertIn("Fish oil reduced triglycerides", article.full_text)
        self.assertEqual(len(article.passages), 2)

    def test_parse_bioc_payload_raises_when_no_passages_exist(self) -> None:
        with self.assertRaises(RuntimeError):
            parse_bioc_payload({"documents": [{"infons": {}, "passages": []}]}, "PMC3572442")

    def test_chunk_article_is_stable_and_preserves_section_metadata(self) -> None:
        article = parse_bioc_payload(
            {
                "documents": [
                    {
                        "infons": {"article-title": "Chunking Test"},
                        "passages": [
                            {
                                "infons": {"section": "Abstract", "type": "abstract"},
                                "text": "Alpha beta gamma delta epsilon zeta eta theta iota kappa.",
                            },
                            {
                                "infons": {"section": "Results", "type": "paragraph"},
                                "text": "Lambda mu nu xi omicron pi rho sigma tau upsilon.",
                            },
                        ],
                    }
                ]
            },
            "PMC111",
        )

        chunks = chunk_article(article, chunk_max_chars=45, overlap_chars=5)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].id, "PMC111-chunk-0001")
        self.assertLess(chunks[1].char_start, chunks[0].char_end)
        self.assertIn(chunks[0].section, {"Abstract", "abstract"})


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = {
            "id": "paper:PMC3572442",
            "pmcid": "PMC3572442",
            "pmid": "12345",
            "title": "Validation paper",
        }
        self.chunk = ChunkRecord(
            id="PMC3572442-chunk-0001",
            document_id="paper:PMC3572442",
            pmcid="PMC3572442",
            order=1,
            char_start=0,
            char_end=64,
            section="Abstract",
            type="abstract",
            source_sections=["Abstract"],
            text="Fish oil reduced triglycerides in adults.",
        )
        self.context = ExtractionContext(
            extractor="fixture",
            model="fixture-model",
            created_at="2026-01-01T00:00:00+00:00",
            min_confidence=0.5,
        )

    def test_validate_extraction_accepts_supported_relationship(self) -> None:
        raw_output = {
            "entities": [
                {"id": "", "type": "Drug", "name": "Fish oil", "properties": {}},
                {"id": "", "type": "Biomarker", "name": "Triglycerides", "properties": {}},
            ],
            "relationships": [
                {
                    "type": "REDUCES",
                    "source": {"id": "", "type": "Drug", "name": "Fish oil"},
                    "target": {"id": "", "type": "Biomarker", "name": "Triglycerides"},
                    "properties": {"confidence": 0.92, "evidence": "Fish oil reduced triglycerides"},
                }
            ],
            "rejected_candidates": [],
        }

        normalized = validate_extraction_output(raw_output, self.document, self.chunk, self.context)

        self.assertEqual(len(normalized["entities"]), 2)
        self.assertEqual(len(normalized["relationships"]), 1)
        relationship = normalized["relationships"][0]
        self.assertEqual(relationship["source"]["id"], "drug:fish_oil")
        self.assertEqual(relationship["properties"]["chunk_id"], "PMC3572442-chunk-0001")
        self.assertEqual(relationship["properties"]["source_pmcid"], "PMC3572442")

    def test_validate_extraction_rejects_bad_direction_missing_evidence_and_low_confidence(self) -> None:
        raw_output = {
            "entities": [],
            "relationships": [
                {
                    "type": "REDUCES",
                    "source": {"id": "", "type": "Biomarker", "name": "Triglycerides"},
                    "target": {"id": "", "type": "Drug", "name": "Fish oil"},
                    "properties": {"confidence": 0.9, "evidence": "bad direction"},
                },
                {
                    "type": "REDUCES",
                    "source": {"id": "", "type": "Drug", "name": "Fish oil"},
                    "target": {"id": "", "type": "Biomarker", "name": "Triglycerides"},
                    "properties": {"confidence": 0.9, "evidence": ""},
                },
                {
                    "type": "REDUCES",
                    "source": {"id": "", "type": "Drug", "name": "Fish oil"},
                    "target": {"id": "", "type": "Biomarker", "name": "Triglycerides"},
                    "properties": {"confidence": 0.1, "evidence": "Fish oil reduced triglycerides"},
                },
            ],
            "rejected_candidates": [],
        }

        normalized = validate_extraction_output(raw_output, self.document, self.chunk, self.context)

        self.assertEqual(normalized["relationships"], [])
        self.assertEqual(len(normalized["rejected_candidates"]), 3)


class OpenAIExtractorTests(unittest.TestCase):
    def test_openai_extractor_uses_responses_api_and_parses_output_text(self) -> None:
        calls: list[dict] = []
        output = {
            "paper": {
                "pmid": "12345",
                "pmcid": "PMC3572442",
                "title": "Mock paper",
                "year": "",
                "journal": "",
                "doi": "",
                "authors": [],
                "abstract": "",
            },
            "entities": [],
            "relationships": [],
            "rejected_candidates": [],
        }

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return types.SimpleNamespace(output_text=json.dumps(output))

        class FakeOpenAI:
            def __init__(self):
                self.responses = FakeResponses()

        fake_openai_module = types.ModuleType("openai")
        fake_openai_module.OpenAI = FakeOpenAI

        with mock.patch.dict(sys.modules, {"openai": fake_openai_module}):
            extractor = OpenAIResponsesExtractor(model="gpt-test", reasoning_effort="low")
            result = extractor.extract(
                {"pmcid": "PMC3572442", "pmid": "12345", "title": "Mock paper", "authors": []},
                ChunkRecord(
                    id="PMC3572442-chunk-0001",
                    document_id="paper:PMC3572442",
                    pmcid="PMC3572442",
                    order=1,
                    char_start=0,
                    char_end=4,
                    section="Abstract",
                    type="abstract",
                    source_sections=["Abstract"],
                    text="Text",
                ),
            )

        self.assertEqual(result["paper"]["pmcid"], "PMC3572442")
        self.assertEqual(calls[0]["model"], "gpt-test")
        self.assertEqual(calls[0]["reasoning"], {"effort": "low"})
        self.assertEqual(calls[0]["text"]["format"]["type"], "json_schema")

    def test_openai_extractor_records_model_call_json_when_enabled(self) -> None:
        output = {
            "paper": {
                "pmid": "12345",
                "pmcid": "PMC3572442",
                "title": "Mock paper",
                "year": "",
                "journal": "",
                "doi": "",
                "authors": [],
                "abstract": "",
            },
            "entities": [],
            "relationships": [],
            "rejected_candidates": [],
        }

        class FakeResponses:
            def create(self, **kwargs):
                return types.SimpleNamespace(output_text=json.dumps(output))

        class FakeOpenAI:
            def __init__(self):
                self.responses = FakeResponses()

        fake_openai_module = types.ModuleType("openai")
        fake_openai_module.OpenAI = FakeOpenAI

        with tempfile.TemporaryDirectory() as tmpdir:
            model_call_root = Path(tmpdir) / "model_calls"
            with mock.patch.dict(sys.modules, {"openai": fake_openai_module}):
                extractor = OpenAIResponsesExtractor(
                    model="gpt-test",
                    reasoning_effort="low",
                    model_call_root=model_call_root,
                )
                extractor.extract(
                    {"pmcid": "PMC3572442", "pmid": "12345", "title": "Mock paper", "authors": []},
                    ChunkRecord(
                        id="PMC3572442-chunk-0001",
                        document_id="paper:PMC3572442",
                        pmcid="PMC3572442",
                        order=1,
                        char_start=0,
                        char_end=4,
                        section="Abstract",
                        type="abstract",
                        source_sections=["Abstract"],
                        text="Text",
                    ),
                )

            self.assertEqual(len(extractor.last_model_call_paths), 1)
            audit_path = Path(extractor.last_model_call_paths[0])
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(audit["provider"], "openai")
        self.assertEqual(audit["model"], "gpt-test")
        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["parsed_json"], output)
        self.assertEqual(audit["request"]["model"], "gpt-test")


class LocalExtractorTests(unittest.TestCase):
    def test_gliner_ollama_extractor_uses_candidates_and_validates_relationships(self) -> None:
        class FakeGLiNER:
            def predict_entities(self, text: str, labels: list[str], threshold: float) -> list[dict[str, object]]:
                self.text = text
                self.labels = labels
                self.threshold = threshold
                return [
                    {"text": "Fish oil", "label": "Drug", "score": 0.91},
                    {"text": "Triglycerides", "label": "Biomarker", "score": 0.88},
                ]

        class FakeLanguageModel:
            provider = "ollama"
            model = "qwen-test"

            def generate_text(self, prompt: str) -> str:
                return ""

            def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, object]:
                self.prompt = prompt
                self.json_schema = json_schema
                return {
                    "relationships": [
                        {
                            "type": "REDUCES",
                            "source": {"type": "Drug", "name": "Fish oil"},
                            "target": {"type": "Biomarker", "name": "Triglycerides"},
                            "properties": {"confidence": 0.86, "evidence": "Fish oil reduced triglycerides"},
                        }
                    ],
                    "rejected_candidates": [],
                }

        chunk = ChunkRecord(
            id="PMC3572442-chunk-0001",
            document_id="paper:PMC3572442",
            pmcid="PMC3572442",
            order=1,
            char_start=0,
            char_end=64,
            section="Abstract",
            type="abstract",
            source_sections=["Abstract"],
            text="Fish oil reduced triglycerides in adults.",
        )
        document = {"id": "paper:PMC3572442", "pmcid": "PMC3572442", "pmid": "12345", "title": "Mock paper"}
        fake_gliner = FakeGLiNER()
        fake_model = FakeLanguageModel()
        extractor = GLiNEROllamaExtractor(
            model="qwen-test",
            entity_model="fake-gliner",
            language_model=fake_model,
            gliner_model=fake_gliner,
        )

        raw_output = extractor.extract(document, chunk)
        normalized = validate_extraction_output(
            raw_output,
            document,
            chunk,
            ExtractionContext(
                extractor=extractor.provider,
                model=extractor.model,
                created_at="2026-01-01T00:00:00+00:00",
            ),
        )

        self.assertEqual(fake_gliner.labels, ["Drug", "Condition", "Symptom", "RiskFactor", "Biomarker"])
        self.assertIn("candidate_entities", fake_model.prompt)
        self.assertEqual(fake_model.json_schema["name"], "medgraphrag_local_relationship_extraction")
        self.assertEqual(len(normalized["entities"]), 2)
        self.assertEqual(len(normalized["relationships"]), 1)
        self.assertEqual(normalized["relationships"][0]["type"], "REDUCES")

    def test_gliner_ollama_extractor_records_entity_and_relationship_calls(self) -> None:
        class FakeGLiNER:
            def predict_entities(self, text: str, labels: list[str], threshold: float) -> list[dict[str, object]]:
                return [
                    {"text": "Fish oil", "label": "Drug", "score": 0.91},
                    {"text": "Triglycerides", "label": "Biomarker", "score": 0.88},
                ]

        class FakeLanguageModel:
            provider = "ollama"
            model = "qwen-test"

            def generate_text(self, prompt: str) -> str:
                return ""

            def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, object]:
                return {
                    "relationships": [
                        {
                            "type": "REDUCES",
                            "source": {"type": "Drug", "name": "Fish oil"},
                            "target": {"type": "Biomarker", "name": "Triglycerides"},
                            "properties": {"confidence": 0.86, "evidence": "Fish oil reduced triglycerides"},
                        }
                    ],
                    "rejected_candidates": [],
                }

        chunk = ChunkRecord(
            id="PMC3572442-chunk-0001",
            document_id="paper:PMC3572442",
            pmcid="PMC3572442",
            order=1,
            char_start=0,
            char_end=64,
            section="Abstract",
            type="abstract",
            source_sections=["Abstract"],
            text="Fish oil reduced triglycerides in adults.",
        )
        document = {"id": "paper:PMC3572442", "pmcid": "PMC3572442", "pmid": "12345", "title": "Mock paper"}

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = GLiNEROllamaExtractor(
                model="qwen-test",
                entity_model="fake-gliner",
                language_model=FakeLanguageModel(),
                gliner_model=FakeGLiNER(),
                model_call_root=Path(tmpdir) / "model_calls",
            )
            extractor.extract(document, chunk)
            audit_payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in extractor.last_model_call_paths]

        self.assertEqual(len(audit_payloads), 2)
        self.assertEqual(audit_payloads[0]["provider"], "gliner")
        self.assertEqual(audit_payloads[0]["parsed_json"]["entities"][0]["name"], "Fish oil")
        self.assertEqual(audit_payloads[1]["provider"], "ollama")
        self.assertEqual(audit_payloads[1]["status"], "ok")


class Neo4jLoaderTests(unittest.TestCase):
    def test_loader_builds_idempotent_paper_entity_mentions_and_relationship_queries(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict]] = []

            def run(self, query: str, **params):
                self.calls.append((query, params))

        session = FakeSession()
        record = {
            "document": {
                "id": "paper:PMC3572442",
                "pmcid": "PMC3572442",
                "pmid": "",
                "title": "Graph paper",
                "chunk_count": 1,
            },
            "chunks": [],
            "entities": [
                {
                    "id": "drug:fish_oil",
                    "type": "Drug",
                    "name": "Fish oil",
                    "properties": {"extractor": "fixture", "model": "fixture-model", "created_at": "now"},
                },
                {
                    "id": "biomarker:triglycerides",
                    "type": "Biomarker",
                    "name": "Triglycerides",
                    "properties": {"extractor": "fixture", "model": "fixture-model", "created_at": "now"},
                },
            ],
            "relationships": [
                {
                    "id": "rel:abc",
                    "type": "REDUCES",
                    "source": {"id": "drug:fish_oil", "type": "Drug", "name": "Fish oil"},
                    "target": {"id": "biomarker:triglycerides", "type": "Biomarker", "name": "Triglycerides"},
                    "properties": {
                        "confidence": 0.9,
                        "evidence": "Fish oil reduced triglycerides",
                        "source_pmcid": "PMC3572442",
                        "chunk_id": "PMC3572442-chunk-0001",
                    },
                }
            ],
        }

        counts = load_processed_record_with_session(session, record)

        self.assertEqual(counts, {"entities": 2, "relationships": 1})
        combined_queries = "\n".join(query for query, _ in session.calls)
        self.assertIn("MERGE (paper:Paper {id: $id})", combined_queries)
        self.assertIn("MERGE (paper)-[mention:MENTIONS", combined_queries)
        self.assertIn("MERGE (source)-[relationship:REDUCES", combined_queries)
        self.assertNotIn("pmid", session.calls[0][1]["props"])


if __name__ == "__main__":
    unittest.main()
