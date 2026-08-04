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
from packages.llm.providers import get_language_model
from packages.qa.answerers import GraphRAGAnswerer
from packages.qa.models import DEFAULT_MAX_EVIDENCE, QuestionRecord
from packages.qa.retrievers import get_retriever


APP_DEFAULT_MODEL_PROFILE = "local-non-instruct"
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


@lru_cache(maxsize=12)
def get_qa_answerer(
    model_profile: str,
    provider: str,
    model_name: str,
    retriever_name: str,
    max_evidence: int,
) -> GraphRAGAnswerer:
    model = get_language_model(provider, model_name)
    retriever = get_retriever(retriever_name)
    return GraphRAGAnswerer(model=model, retriever=retriever, max_evidence=max_evidence)


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


def get_active_model_runtime() -> dict:
    return {"activeProfile": get_app_model_profile().to_dict()}


def answer_question(question: str, model_profile: str | None = None) -> dict:
    _ = model_profile
    profile = get_app_model_profile()
    max_evidence = int(os.getenv("QA_MAX_EVIDENCE", str(DEFAULT_MAX_EVIDENCE)))
    answerer = get_qa_answerer(
        profile.name,
        profile.qa_provider,
        profile.qa_model,
        profile.qa_retriever,
        max_evidence,
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
