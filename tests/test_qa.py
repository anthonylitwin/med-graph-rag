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
from experiments.run_qa_eval import load_qa_eval_config
from pipelines.qa.evaluation import QAEvaluationConfig, run_qa_evaluation
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


class QAEvaluationTests(unittest.TestCase):
    def test_qa_eval_params_loader_maps_dvc_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            params_path = Path(tmpdir) / "params.yaml"
            params_path.write_text(
                json.dumps(
                    {
                        "qa_eval": {
                            "eval_id": "qa-test",
                            "question_file": "eval/questions/qa_eval_v001.json",
                            "output_root": "data/qa/eval_v001",
                            "graph_run_id": "graph-run",
                            "graph_source": "fixture graph",
                            "model_profile": "frontier",
                            "model": "model-x",
                            "retriever": "graph",
                            "max_evidence": 5,
                            "skip_answer": True,
                            "limit": 1,
                            "fail_fast": True,
                            "llm_judge": {
                                "enabled": True,
                                "provider": "noop",
                                "model": "noop-judge",
                            },
                            "mlflow": {
                                "enabled": False,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = load_qa_eval_config(params_path)

        self.assertEqual(config.eval_id, "qa-test")
        self.assertTrue(config.question_file.is_absolute())
        self.assertEqual(config.graph_run_id, "graph-run")
        self.assertEqual(config.model, "model-x")
        self.assertEqual(config.retriever, "graph")
        self.assertEqual(config.max_evidence, 5)
        self.assertTrue(config.skip_answer)
        self.assertEqual(config.limit, 1)
        self.assertTrue(config.llm_judge_enabled)
        self.assertEqual(config.llm_judge_provider, "noop")
        self.assertEqual(config.llm_judge_model, "noop-judge")

    def test_run_qa_evaluation_writes_metrics_manifest_and_question_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            question_file = tmp_path / "questions.json"
            question_file.write_text(
                json.dumps(
                    {
                        "question_set_id": "fixture_qa_gold",
                        "questions": [
                            {
                                "id": "q1",
                                "question": "What medication may aspirin interact with?",
                                "expected_facts": ["Aspirin may interact with anticoagulant medication."],
                                "expected_entities": ["Aspirin", "Anticoagulant medication"],
                                "expected_relationships": ["MAY_INTERACT_WITH"],
                                "expected_evidence_ids": ["noop:aspirin-interaction"],
                                "question_type": "direct_relationship",
                                "split": "dev",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = run_qa_evaluation(
                QAEvaluationConfig(
                    question_file=question_file,
                    output_root=tmp_path / "eval",
                    eval_id="qa-fixture",
                    graph_run_id="fixture-graph",
                    graph_source="noop",
                    model_profile="noop",
                    force=True,
                )
            )
            eval_root = tmp_path / "eval" / "qa-fixture"
            metrics = json.loads((eval_root / "metrics.json").read_text(encoding="utf-8"))
            question_results_exists = (eval_root / "question_results.csv").exists()
            artifact_manifest_exists = (eval_root / "artifact_manifest.json").exists()

        self.assertEqual(result["question_set_id"], "fixture_qa_gold")
        self.assertEqual(metrics["overall"]["retrieval_recall"], 1.0)
        self.assertEqual(metrics["overall"]["answer_accuracy"], 1.0)
        self.assertEqual(result["graph_provenance"]["graph_run_id"], "fixture-graph")
        self.assertTrue(question_results_exists)
        self.assertTrue(artifact_manifest_exists)

    def test_run_qa_evaluation_scores_unanswerable_abstention(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            question_file = tmp_path / "questions.json"
            question_file.write_text(
                json.dumps(
                    [
                        {
                            "id": "q1",
                            "question": "What treatment cures the sample-only condition?",
                            "expected_abstention": True,
                            "question_type": "unanswerable",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = run_qa_evaluation(
                QAEvaluationConfig(
                    question_file=question_file,
                    output_root=tmp_path / "eval",
                    eval_id="qa-unanswerable",
                    model_profile="noop",
                    force=True,
                )
            )

        self.assertEqual(result["metrics"]["overall"]["abstention_accuracy"], 1.0)
        self.assertEqual(result["metrics"]["overall"]["answer_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
