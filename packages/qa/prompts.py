from __future__ import annotations

import json

from packages.qa.models import RetrievedEvidence


def qa_answer_json_schema() -> dict:
    string = {"type": "string"}
    source = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "documentId": string,
            "title": string,
            "evidenceText": string,
            "confidence": {"type": "number"},
            "sourcePmcid": string,
            "chunkId": string,
        },
        "required": ["documentId", "title", "evidenceText", "confidence", "sourcePmcid", "chunkId"],
    }
    reasoning_step = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "source": string,
            "relationship": string,
            "target": string,
        },
        "required": ["source", "relationship", "target"],
    }
    return {
        "type": "json_schema",
        "name": "medgraphrag_qa_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": string,
                "sources": {"type": "array", "items": source},
                "reasoningPath": {"type": "array", "items": reasoning_step},
                "confidence": {"type": "number"},
                "abstained": {"type": "boolean"},
            },
            "required": ["answer", "sources", "reasoningPath", "confidence", "abstained"],
        },
    }


def format_qa_prompt(question: str, evidence: list[RetrievedEvidence]) -> str:
    evidence_payload = [item.to_dict() for item in evidence]
    return (
        "You are the question-answering component for MedGraphRAG.\n"
        "Answer biomedical questions using only the retrieved graph evidence below.\n"
        "Do not use outside medical knowledge. If the evidence is insufficient, set abstained to true and say what is missing.\n"
        "Keep the answer concise, factual, and cite the returned evidence objects in sources.\n\n"
        f"Question:\n{question}\n\n"
        "Retrieved graph evidence as JSON:\n"
        f"{json.dumps(evidence_payload, indent=2)}\n"
    )
