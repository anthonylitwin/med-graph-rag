from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from packages.llm.providers import NoopLanguageModel
from packages.qa.answerers import GraphRAGAnswerer
from packages.qa.datasets import collect_questions, read_training_dataset, to_openai_finetune_record
from packages.qa.models import QAConfig, QuestionRecord, RetrievedEvidence
from packages.qa.retrievers import NoopRetriever, evidence_from_record
from pipelines.qa.pipeline import process_questions


class QADatasetTests(unittest.TestCase):
    def test_collect_questions_reads_eval_shape_and_cli_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "questions.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "q1",
                            "question": "What medication may aspirin interact with?",
                            "expected_facts": ["Aspirin may interact with anticoagulant medication."],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            questions = collect_questions([["What risk may aspirin increase?"]], path)

        self.assertEqual([question.id for question in questions], ["q1", "q0002"])
        self.assertEqual(questions[0].expected_facts, ["Aspirin may interact with anticoagulant medication."])

    def test_training_dataset_exports_openai_messages_from_expected_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "train.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "q1",
                            "question": "What risk may aspirin increase?",
                            "expected_facts": ["Aspirin may increase bleeding risk."],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            example = read_training_dataset(path)[0]
            exported = to_openai_finetune_record(example)

        self.assertEqual(example.answer, "Aspirin may increase bleeding risk.")
        self.assertEqual(exported["messages"][1]["role"], "user")
        self.assertEqual(exported["messages"][2]["content"], "Aspirin may increase bleeding risk.")


class QAAnswererTests(unittest.TestCase):
    def test_noop_model_builds_deterministic_answer_from_evidence(self) -> None:
        answerer = GraphRAGAnswerer(model=NoopLanguageModel(), retriever=NoopRetriever())

        answer = answerer.answer(QuestionRecord(id="q1", question="What risk may aspirin increase?"))

        self.assertFalse(answer.abstained)
        self.assertIn("Aspirin may increase the risk of Bleeding risk.", answer.answer)
        self.assertEqual(answer.reasoning_path[0]["relationship"], "MAY_INCREASE_RISK_OF")

    def test_model_json_response_is_normalized(self) -> None:
        class FakeRetriever:
            name = "fixture"

            def retrieve(self, question: str, limit: int) -> list[RetrievedEvidence]:
                return [
                    RetrievedEvidence(
                        id="e1",
                        source_name="Fish oil",
                        source_labels=["Drug"],
                        relationship_type="REDUCES",
                        target_name="Triglycerides",
                        target_labels=["Biomarker"],
                        evidence_text="Fish oil reduced triglycerides.",
                        confidence=0.92,
                    )
                ]

        class FakeModel:
            provider = "fixture"
            model = "fixture-model"

            def generate_text(self, prompt: str) -> str:
                return ""

            def generate_json(self, prompt: str, json_schema: dict[str, Any] | None = None) -> dict[str, Any]:
                self.prompt = prompt
                self.json_schema = json_schema
                return {
                    "answer": "Fish oil may reduce triglycerides.",
                    "sources": [],
                    "reasoningPath": [],
                    "confidence": 0.8,
                    "abstained": False,
                }

        model = FakeModel()
        answerer = GraphRAGAnswerer(model=model, retriever=FakeRetriever())
        answer = answerer.answer(QuestionRecord(id="q1", question="What does fish oil reduce?"))

        self.assertEqual(answer.answer, "Fish oil may reduce triglycerides.")
        self.assertEqual(answer.confidence, 0.8)
        self.assertIn("Retrieved graph evidence", model.prompt)
        self.assertEqual(model.json_schema["name"], "medgraphrag_qa_answer")


class QARetrieverTests(unittest.TestCase):
    def test_evidence_from_record_maps_neo4j_fields(self) -> None:
        evidence = evidence_from_record(
            {
                "relationshipId": "rel:1",
                "sourceName": "Statins",
                "sourceLabels": ["Drug"],
                "relationshipType": "REDUCES",
                "evidenceText": "Statins lower LDL cholesterol.",
                "confidence": 0.95,
                "sourcePmcid": "PMC1",
                "sourcePmid": "123",
                "chunkId": "PMC1-chunk-0001",
                "documentId": "paper:PMC1",
                "documentTitle": "A paper",
                "targetName": "LDL cholesterol",
                "targetLabels": ["Biomarker"],
            }
        )

        self.assertEqual(evidence.id, "rel:1")
        self.assertEqual(evidence.confidence, 0.95)
        self.assertEqual(evidence.to_dict()["sourcePmcid"], "PMC1")


class QAPipelineTests(unittest.TestCase):
    def test_process_questions_writes_manifest_retrieval_and_answer_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "qa"
            results = process_questions(
                QAConfig(
                    questions=[QuestionRecord(id="q1", question="What medication may aspirin interact with?")],
                    output_root=output_root,
                    answerer_provider="noop",
                    model="noop-language-model-v0",
                    retriever="noop",
                )
            )

            manifest_path = output_root / "manifest.csv"
            answer_path = output_root / "answers" / "q1.json"
            retrieved_path = output_root / "retrieved" / "q1.json"
            with manifest_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            answer_exists = answer_path.exists()
            retrieved_exists = retrieved_path.exists()

        self.assertEqual(results[0].status, "ok")
        self.assertEqual(rows[0]["retrieved_count"], "1")
        self.assertTrue(answer_exists)
        self.assertTrue(retrieved_exists)


if __name__ == "__main__":
    unittest.main()
