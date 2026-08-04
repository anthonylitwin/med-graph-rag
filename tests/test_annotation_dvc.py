from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from experiments.run_annotation_eval import PROJECT_ROOT, load_annotation_eval_config


class AnnotationDvcConfigTests(unittest.TestCase):
    def test_repository_params_load_as_artifact_only_full_evaluation(self) -> None:
        config = load_annotation_eval_config(PROJECT_ROOT / "experiments" / "params.yaml")

        self.assertTrue(config.eval_id)
        self.assertTrue(config.model_profile)
        self.assertIsNone(config.limit)
        self.assertTrue(config.force)
        self.assertEqual(config.entity_threshold, 0.5)
        self.assertGreaterEqual(config.relation_threshold, 0.0)
        self.assertLessEqual(config.relation_threshold, 1.0)
        self.assertEqual(config.concept_threshold, 0.84)
        self.assertEqual(config.max_pair_distance, 300)
        self.assertTrue(config.terminology_path.is_absolute())
        self.assertEqual(config.neo4j_load_mode, "none")
        self.assertIsInstance(config.mlflow, bool)
        self.assertTrue(config.gold_manifest_path.is_absolute())
        self.assertTrue(config.output_root.is_absolute())

    def test_optional_model_limit_and_mlflow_values_are_mapped(self) -> None:
        payload = {
            "annotation_eval": {
                "eval_id": "local-test",
                "gold_manifest": "data/gold.json",
                "output_root": "data/evals",
                "model_profile": "local-qwen25",
                "model": "qwen-custom",
                "entity_model": "medical-ner-custom",
                "min_confidence": 0.7,
                "non_instruct": {
                    "entity_threshold": 0.41,
                    "concept_threshold": 0.81,
                    "relation_threshold": 0.63,
                },
                "limit": 3,
                "fail_fast": True,
                "neo4j_load_mode": "none",
                "mlflow": {
                    "enabled": True,
                    "tracking_uri": "http://mlflow.test",
                    "experiment": "annotation-test",
                    "run_name": "local-test",
                    "log_artifacts": False,
                },
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            params_path = Path(temp_dir) / "params.yaml"
            params_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
            config = load_annotation_eval_config(params_path)

        self.assertEqual(config.model, "qwen-custom")
        self.assertEqual(config.entity_model, "medical-ner-custom")
        self.assertEqual(config.entity_threshold, 0.41)
        self.assertEqual(config.concept_threshold, 0.81)
        self.assertEqual(config.relation_threshold, 0.63)
        self.assertEqual(config.limit, 3)
        self.assertTrue(config.fail_fast)
        self.assertTrue(config.mlflow)
        self.assertEqual(config.mlflow_run_name, "local-test")
        self.assertFalse(config.mlflow_log_artifacts)

    def test_eval_id_is_required_for_dvc_output(self) -> None:
        payload = {
            "annotation_eval": {
                "gold_manifest": "data/gold.json",
                "output_root": "data/evals",
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            params_path = Path(temp_dir) / "params.yaml"
            params_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "eval_id is required"):
                load_annotation_eval_config(params_path)


if __name__ == "__main__":
    unittest.main()
