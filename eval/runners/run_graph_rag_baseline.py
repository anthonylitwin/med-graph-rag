from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.llm.profiles import resolve_model_profile
from packages.qa.datasets import read_question_file
from packages.qa.models import QAConfig
from pipelines.qa.pipeline import process_questions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the GraphRAG QA baseline over an evaluation set")
    parser.add_argument("--question-file", type=Path, default=Path("eval/questions/qa_eval_v001.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/qa/eval_graph_rag_v001"))
    parser.add_argument("--model-profile", default=os.getenv("MODEL_PROFILE", "noop"))
    parser.add_argument("--answerer", choices=["openai", "ollama", "local", "fine_tuned", "noop"])
    parser.add_argument("--model")
    parser.add_argument("--retriever", choices=["graph", "noop"])
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = resolve_model_profile(
        args.model_profile,
        qa_provider=args.answerer,
        qa_model=args.model,
        qa_retriever=args.retriever,
    )
    questions = read_question_file(args.question_file, args.limit)
    results = process_questions(
        QAConfig(
            questions=questions,
            output_root=args.output_root,
            model_profile=profile.name,
            answerer_provider=profile.qa_provider,
            model=profile.qa_model,
            retriever=profile.qa_retriever,
            limit=args.limit,
        )
    )
    summary = {
        "question_count": len(results),
        "success_count": sum(1 for result in results if result.status == "ok"),
        "abstained_count": sum(1 for result in results if result.abstained),
        "manifest": (args.output_root / "manifest.csv").as_posix(),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
