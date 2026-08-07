from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
import sys


def _ensure_repo_root_on_path() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "packages").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return


_ensure_repo_root_on_path()

from packages.llm.profiles import ModelProfile, resolve_model_profile
from packages.llm.providers import LocalHTTPModel, OllamaChatModel, get_language_model
from packages.qa.answerers import GraphRAGAnswerer
from packages.qa.models import DEFAULT_MAX_EVIDENCE, QuestionRecord
from packages.qa.retrievers import get_retriever


APP_DEFAULT_MODEL_PROFILE = "local-non-instruct"
APP_QA_GRAPH_RUN_ID_ENV = "QA_GRAPH_RUN_ID"
APP_QA_PARAMS_PATH_ENV = "QA_PARAMS_PATH"
_EXPERIMENT_ONLY_APP_PROFILES = {"frontier", "local-qwen25", "local-qwen3"}
_LOCAL_QA_PROVIDERS = {"ollama", "local", "noop", "none"}
_LOCAL_EXTRACTOR_PROVIDERS = {
    "gliner",
    "gliner_ner",
    "gliner-ner",
    "non_instruct",
    "non-instruct",
    "gliner_semantic",
    "gliner-semantic",
    "noop",
    "none",
}
APP_QA_MODEL_TIMEOUT_SECONDS = 90


@lru_cache(maxsize=12)
def get_qa_answerer(
    model_profile: str,
    provider: str,
    model_name: str,
    retriever_name: str,
    graph_run_id: str,
    max_evidence: int,
    model_timeout_seconds: int,
) -> GraphRAGAnswerer:
    model = get_app_language_model(provider, model_name, model_timeout_seconds)
    retriever = get_retriever(retriever_name, graph_run_id=graph_run_id)
    return GraphRAGAnswerer(model=model, retriever=retriever, max_evidence=max_evidence)


def get_app_language_model(provider: str, model_name: str, timeout_seconds: int):
    normalized = provider.lower().strip()
    if normalized == "ollama":
        return OllamaChatModel(model=model_name, timeout_seconds=timeout_seconds)
    if normalized == "local":
        return LocalHTTPModel(model=model_name, timeout_seconds=timeout_seconds)
    return get_language_model(provider, model_name)


def _local_env_model(provider: str) -> str | None:
    normalized = provider.lower().strip()
    if normalized in {"ollama", "local"}:
        return os.getenv("LOCAL_MODEL") or None
    return None


def _validate_app_profile(profile: ModelProfile) -> None:
    if profile.name in _EXPERIMENT_ONLY_APP_PROFILES:
        raise ValueError(f"Model profile '{profile.name}' is reserved for experiments and cannot run the app.")

    qa_provider = profile.qa_provider.lower().strip()
    extractor_provider = profile.extractor_provider.lower().strip()
    if qa_provider not in _LOCAL_QA_PROVIDERS:
        raise ValueError(f"App QA provider must be local-only; got '{profile.qa_provider}'.")
    if extractor_provider not in _LOCAL_EXTRACTOR_PROVIDERS:
        raise ValueError(f"App extractor provider must be local-only; got '{profile.extractor_provider}'.")


def get_app_model_profile() -> ModelProfile:
    app_profile_name = os.getenv("APP_MODEL_PROFILE") or APP_DEFAULT_MODEL_PROFILE
    base_profile = resolve_model_profile(app_profile_name)
    profile = resolve_model_profile(
        app_profile_name,
        qa_model=_local_env_model(base_profile.qa_provider),
        entity_model=os.getenv("EXTRACTOR_ENTITY_MODEL") or None,
    )
    _validate_app_profile(profile)
    return profile


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "experiments" / "params.yaml").exists():
            return parent
    return Path.cwd()


def _read_promoted_graph_run_id() -> str:
    params_path = Path(os.getenv(APP_QA_PARAMS_PATH_ENV) or (_repo_root() / "experiments" / "params.yaml"))
    if not params_path.exists():
        return ""
    try:
        import yaml

        payload = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    qa_eval = payload.get("qa_eval", {}) if isinstance(payload, dict) else {}
    if not isinstance(qa_eval, dict):
        return ""
    return str(qa_eval.get("graph_run_id") or "").strip()


def get_app_graph_run_id() -> str:
    if APP_QA_GRAPH_RUN_ID_ENV in os.environ:
        return str(os.getenv(APP_QA_GRAPH_RUN_ID_ENV) or "").strip()
    return _read_promoted_graph_run_id()


def get_active_model_runtime() -> dict:
    return {
        "activeProfile": get_app_model_profile().to_dict(),
        "graphRunId": get_app_graph_run_id(),
    }


def answer_question(question: str, model_profile: str | None = None) -> dict:
    _ = model_profile
    profile = get_app_model_profile()
    graph_run_id = get_app_graph_run_id()
    max_evidence = int(os.getenv("QA_MAX_EVIDENCE", str(DEFAULT_MAX_EVIDENCE)))
    model_timeout_seconds = int(os.getenv("APP_QA_MODEL_TIMEOUT_SECONDS", str(APP_QA_MODEL_TIMEOUT_SECONDS)))
    answerer = get_qa_answerer(
        profile.name,
        profile.qa_provider,
        profile.qa_model,
        profile.qa_retriever,
        graph_run_id,
        max_evidence,
        model_timeout_seconds,
    )
    record = QuestionRecord(id="ui-question", question=question)
    answer = answerer.answer(record)
    payload = answer.to_dict()
    return {
        "answer": payload["answer"],
        "sources": payload["sources"],
        "reasoningPath": payload["reasoningPath"],
        "model": payload["model"],
        "provider": payload["provider"],
        "modelProfile": profile.name,
        "confidence": payload["confidence"],
        "abstained": payload["abstained"],
    }
