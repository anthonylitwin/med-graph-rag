from __future__ import annotations

import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.qa_service import answer_question, get_active_model_runtime, get_app_model_profile
from app.services.ingestion_service import IngestionJobStore, IngestionQueueService
from pipelines.ingestion.models import ArticlePipelineResult
from app.routes import graph as graph_routes
from app.routes import ingestion as ingestion_routes


class _FakeResult:
    def __init__(self, record: dict | None) -> None:
        self.record = record

    def single(self) -> dict | None:
        return self.record


class _FakeSession:
    def __init__(self, record: dict | None) -> None:
        self.record = record
        self.params = {}

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def run(self, query: str, **params: object) -> _FakeResult:
        self.params = params
        return _FakeResult(self.record)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self.closed = False

    def session(self) -> _FakeSession:
        return self._session

    def close(self) -> None:
        self.closed = True


class ChatServiceTests(unittest.TestCase):
    def test_app_model_runtime_defaults_to_local_non_instruct(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            profile = get_app_model_profile()

        self.assertEqual(profile.name, "local-non-instruct")
        self.assertEqual(profile.qa_provider, "ollama")
        self.assertEqual(profile.extractor_provider, "non_instruct")

    def test_app_model_runtime_uses_launch_time_local_model(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"APP_MODEL_PROFILE": "local-non-instruct", "LOCAL_MODEL": "qwen-custom"},
            clear=True,
        ):
            profile = get_app_model_profile()

        self.assertEqual(profile.name, "local-non-instruct")
        self.assertEqual(profile.qa_model, "qwen-custom")

    def test_model_options_reports_only_active_runtime(self) -> None:
        with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": "noop"}, clear=True):
            runtime = get_active_model_runtime()

        self.assertEqual(runtime["activeProfile"]["name"], "noop")
        self.assertNotIn("profiles", runtime)

    def test_answer_question_honors_noop_profile_metadata(self) -> None:
        with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": "noop"}, clear=True):
            result = answer_question("What risk may aspirin increase?", model_profile="frontier")

        self.assertEqual(result["provider"], "noop")
        self.assertEqual(result["modelProfile"], "noop")
        self.assertEqual(result["model"], "noop-language-model-v0")
        self.assertFalse(result["abstained"])

    def test_app_model_runtime_rejects_experiment_profiles(self) -> None:
        for profile_name in ("frontier", "openai", "api", "local-qwen25", "local-qwen3"):
            with self.subTest(profile_name=profile_name):
                with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": profile_name}, clear=True):
                    with self.assertRaisesRegex(ValueError, "reserved for experiments"):
                        get_app_model_profile()

    def test_chat_page_does_not_render_model_selector(self) -> None:
        chat_page = (PROJECT_ROOT / "apps" / "web" / "src" / "routes" / "ChatPage.vue").read_text(encoding="utf-8")

        self.assertNotIn("<select", chat_page)
        self.assertNotIn("getChatModelOptions", chat_page)
        self.assertNotIn("v-model=\"modelProfile\"", chat_page)

    def test_chat_request_payload_contains_only_message(self) -> None:
        api_client = (PROJECT_ROOT / "apps" / "web" / "src" / "lib" / "apiClient.ts").read_text(encoding="utf-8")
        chat_request_type = api_client.split("export type ChatResponse", maxsplit=1)[0]

        self.assertIn("message: string;", chat_request_type)
        self.assertNotIn("modelProfile?:", chat_request_type)


class IngestionQueueTests(unittest.TestCase):
    def test_create_pmc_job_normalizes_and_persists_document_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                os.environ,
                {
                    "APP_MODEL_PROFILE": "noop",
                    "INGESTION_OUTPUT_ROOT": str(Path(tmpdir) / "outputs"),
                },
                clear=False,
            ):
                service = IngestionQueueService(
                    store=IngestionJobStore(Path(tmpdir) / "jobs.sqlite"),
                    poll_interval_seconds=0.01,
                )
                job = service.create_job(
                    source_type="pmc",
                    pmcids=["3572442", "PMC3572442", "PMC3234107"],
                    model_profile="noop",
                    skip_load=True,
                )

                loaded = service.get_job(job["id"])

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["status"], "queued")
        self.assertEqual(loaded["progressTotal"], 2)
        self.assertEqual(loaded["modelProfile"], "noop")
        self.assertEqual([document["documentKey"] for document in loaded["documents"]], ["PMC3572442", "PMC3234107"])

    def test_worker_records_pmc_job_progress_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                os.environ,
                {
                    "APP_MODEL_PROFILE": "noop",
                    "INGESTION_OUTPUT_ROOT": str(Path(tmpdir) / "outputs"),
                },
                clear=False,
            ):
                service = IngestionQueueService(
                    store=IngestionJobStore(Path(tmpdir) / "jobs.sqlite"),
                    poll_interval_seconds=0.01,
                )
                job = service.create_job(
                    source_type="pmc",
                    pmcids=["PMC3572442"],
                    model_profile="noop",
                    skip_load=True,
                )

                def fake_process(config, progress_callback=None):
                    result = ArticlePipelineResult(
                        pmcid="PMC3572442",
                        pmid="12345",
                        title="Mock article",
                        raw_path=config.output_root / "raw" / "PMC3572442.json",
                        text_path=config.output_root / "text" / "PMC3572442.txt",
                        processed_path=config.output_root / "processed" / "PMC3572442.json",
                        chunk_count=2,
                        entity_count=3,
                        relationship_count=1,
                        fetch_status="ok",
                        extract_status="ok",
                        load_status="skipped",
                        status="ok",
                    )
                    if progress_callback is not None:
                        progress_callback({"event": "article_started", "pmcid": "PMC3572442"})
                        progress_callback({"event": "article_finished", "pmcid": "PMC3572442", "result": result})
                    return [result]

                with mock.patch("app.services.ingestion_service.process_pmc_articles", fake_process):
                    did_run = service.run_next_job_once()

                loaded = service.get_job(job["id"])

        self.assertTrue(did_run)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["status"], "completed")
        self.assertEqual(loaded["progressCurrent"], 1)
        self.assertEqual(loaded["documents"][0]["status"], "completed")
        self.assertEqual(loaded["documents"][0]["entityCount"], 3)

    def test_ingestion_model_options_reports_only_active_runtime(self) -> None:
        with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": "noop"}, clear=True):
            runtime = ingestion_routes.ingestion_model_options()

        self.assertEqual(runtime["activeProfile"]["name"], "noop")
        self.assertNotIn("profiles", runtime)

    def test_create_job_without_model_profile_uses_app_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                os.environ,
                {
                    "APP_MODEL_PROFILE": "noop",
                    "INGESTION_OUTPUT_ROOT": str(Path(tmpdir) / "outputs"),
                },
                clear=False,
            ):
                service = IngestionQueueService(
                    store=IngestionJobStore(Path(tmpdir) / "jobs.sqlite"),
                    poll_interval_seconds=0.01,
                )
                job = service.create_job(
                    source_type="pmc",
                    pmcids=["PMC3572442"],
                    skip_load=True,
                )

        self.assertEqual(job["modelProfile"], "noop")

    def test_create_job_rejects_non_app_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = IngestionQueueService(
                store=IngestionJobStore(Path(tmpdir) / "jobs.sqlite"),
                poll_interval_seconds=0.01,
            )
            for profile_name in ("frontier", "local-qwen25", "local-qwen3"):
                with self.subTest(profile_name=profile_name):
                    with mock.patch.dict(os.environ, {"APP_MODEL_PROFILE": "noop"}, clear=True):
                        with self.assertRaisesRegex(ValueError, "server-configured application model profile"):
                            service.create_job(
                                source_type="pmc",
                                pmcids=["PMC3572442"],
                                model_profile=profile_name,
                                skip_load=True,
                            )

    def test_create_job_accepts_explicit_active_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                os.environ,
                {
                    "APP_MODEL_PROFILE": "noop",
                    "INGESTION_OUTPUT_ROOT": str(Path(tmpdir) / "outputs"),
                },
                clear=False,
            ):
                service = IngestionQueueService(
                    store=IngestionJobStore(Path(tmpdir) / "jobs.sqlite"),
                    poll_interval_seconds=0.01,
                )
                job = service.create_job(
                    source_type="pmc",
                    pmcids=["PMC3572442"],
                    model_profile="noop",
                    skip_load=True,
                )

        self.assertEqual(job["modelProfile"], "noop")

    def test_ingestion_page_does_not_render_model_selector(self) -> None:
        ingestion_page = (PROJECT_ROOT / "apps" / "web" / "src" / "routes" / "IngestionPage.vue").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("<select", ingestion_page)
        self.assertNotIn("v-model=\"selectedModelProfile\"", ingestion_page)

    def test_ingestion_submit_payload_omits_model_profile(self) -> None:
        ingestion_page = (PROJECT_ROOT / "apps" / "web" / "src" / "routes" / "IngestionPage.vue").read_text(
            encoding="utf-8"
        )
        submit_block = ingestion_page.split("const job = await createIngestionJob(", maxsplit=1)[1].split(
            "})",
            maxsplit=1,
        )[0]

        self.assertNotIn("modelProfile", submit_block)


class GraphRouteTests(unittest.TestCase):
    def test_browse_graph_serializes_nodes_relationships_and_metadata(self) -> None:
        session = _FakeSession(
            {
                "nodes": [
                    {
                        "id": "drug-1",
                        "labels": ["Drug"],
                        "properties": {"name": "Aspirin"},
                    },
                    {
                        "id": "condition-1",
                        "labels": ["Condition"],
                        "properties": {"name": "Bleeding risk"},
                    },
                ],
                "relationshipRows": [
                    {
                        "sourceId": "drug-1",
                        "targetId": "condition-1",
                        "type": "INCREASES_RISK_OF",
                        "properties": {"evidence": "sample evidence"},
                    }
                ],
            }
        )
        driver = _FakeDriver(session)

        with mock.patch("app.routes.graph.get_driver", return_value=driver):
            response = graph_routes.browse_graph(
                q="Aspirin",
                label="Drug",
                relationship_type="increases_risk_of",
                pmcid="PMC3572442",
                limit=10,
            )

        self.assertTrue(driver.closed)
        self.assertEqual(response["metadata"]["q"], "aspirin")
        self.assertEqual(response["metadata"]["label"], "Drug")
        self.assertEqual(response["metadata"]["relationshipType"], "INCREASES_RISK_OF")
        self.assertEqual(response["metadata"]["pmcid"], "PMC3572442")
        self.assertEqual(response["metadata"]["nodeCount"], 2)
        self.assertEqual(response["metadata"]["relationshipCount"], 1)
        self.assertEqual(response["relationships"][0]["source"], "drug-1")
        self.assertEqual(session.params["limit"], 10)
        self.assertEqual(session.params["relationship_limit"], 30)

    def test_browse_graph_rejects_unknown_filters(self) -> None:
        with self.assertRaisesRegex(Exception, "Unsupported graph label"):
            graph_routes.browse_graph(q=None, label="UnknownLabel")

        with self.assertRaisesRegex(Exception, "Unsupported graph relationship type"):
            graph_routes.browse_graph(
                q=None,
                label=None,
                relationship_type="BAD_RELATIONSHIP",
            )


if __name__ == "__main__":
    unittest.main()
