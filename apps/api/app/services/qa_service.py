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

from packages.llm.models import DEFAULT_FRONTIER_MODEL
from packages.llm.providers import get_language_model
from packages.qa.answerers import GraphRAGAnswerer
from packages.qa.models import DEFAULT_MAX_EVIDENCE, QuestionRecord
from packages.qa.retrievers import get_retriever


@lru_cache(maxsize=1)
def get_qa_answerer() -> GraphRAGAnswerer:
    provider = os.getenv("QA_PROVIDER", "openai")
    model_name = os.getenv("QA_MODEL") or os.getenv("OPENAI_MODEL", DEFAULT_FRONTIER_MODEL)
    retriever_name = os.getenv("QA_RETRIEVER", "graph")
    max_evidence = int(os.getenv("QA_MAX_EVIDENCE", str(DEFAULT_MAX_EVIDENCE)))
    model = get_language_model(provider, model_name)
    retriever = get_retriever(retriever_name)
    return GraphRAGAnswerer(model=model, retriever=retriever, max_evidence=max_evidence)


def answer_question(question: str) -> dict:
    answerer = get_qa_answerer()
    record = QuestionRecord(id="ui-question", question=question)
    answer = answerer.answer(record)
    payload = answer.to_dict()
    return {
        "answer": payload["answer"],
        "sources": payload["sources"],
        "reasoningPath": payload["reasoningPath"],
        "model": payload["model"],
        "confidence": payload["confidence"],
        "abstained": payload["abstained"],
    }
