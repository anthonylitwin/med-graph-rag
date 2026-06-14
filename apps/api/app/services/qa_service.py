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

from packages.llm.profiles import ModelProfile, default_model_profile_name, list_model_profiles, resolve_model_profile
from packages.llm.providers import get_language_model
from packages.qa.answerers import GraphRAGAnswerer
from packages.qa.models import DEFAULT_MAX_EVIDENCE, QuestionRecord
from packages.qa.retrievers import get_retriever


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


def get_model_options() -> dict:
    return {
        "defaultProfile": default_model_profile_name(),
        "profiles": [profile.to_dict() for profile in list_model_profiles()],
    }


def _qa_profile(model_profile: str | None = None) -> ModelProfile:
    return resolve_model_profile(model_profile)


def answer_question(question: str, model_profile: str | None = None) -> dict:
    profile = _qa_profile(model_profile)
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
