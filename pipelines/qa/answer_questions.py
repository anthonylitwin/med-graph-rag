from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.llm.profiles import resolve_model_profile
from packages.qa.datasets import collect_questions
from packages.qa.models import DEFAULT_MAX_EVIDENCE, DEFAULT_QA_OUTPUT_ROOT, QAConfig
from pipelines.qa.pipeline import process_questions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Answer biomedical questions using MedGraphRAG")
    parser.add_argument(
        "--question",
        action="append",
        nargs="+",
        dest="question_groups",
        help="Question text. Can be repeated or space-separated when quoted.",
    )
    parser.add_argument("--question-file", type=Path, help="JSON or JSONL file containing question records.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_QA_OUTPUT_ROOT)
    parser.add_argument("--clean-output", action="store_true", help="Delete output directory before writing artifacts")
    parser.add_argument("--model-profile", help="Runtime profile: frontier, local-qwen25, local-qwen3, or noop.")
    parser.add_argument("--answerer", choices=["openai", "ollama", "local", "fine_tuned", "noop"], help="Override the profile QA provider.")
    parser.add_argument("--model", help="Override the profile QA model.")
    parser.add_argument("--retriever", choices=["graph", "noop"], help="Override the profile QA retriever.")
    parser.add_argument("--max-evidence", type=int, default=int(os.getenv("QA_MAX_EVIDENCE", DEFAULT_MAX_EVIDENCE)))
    parser.add_argument("--skip-answer", action="store_true", help="Only retrieve and write evidence artifacts.")
    parser.add_argument("--fail-fast", action="store_true")
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
    questions = collect_questions(args.question_groups, args.question_file, args.limit)
    config = QAConfig(
        questions=questions,
        output_root=args.output_root,
        clean_output=args.clean_output,
        model_profile=profile.name,
        answerer_provider=profile.qa_provider,
        model=profile.qa_model,
        retriever=profile.qa_retriever,
        max_evidence=args.max_evidence,
        skip_answer=args.skip_answer,
        fail_fast=args.fail_fast,
        limit=args.limit,
    )
    results = process_questions(config)
    success_count = sum(1 for result in results if result.status == "ok")
    manifest_path = args.output_root / "manifest.csv"
    print(f"Answered {success_count}/{len(results)} question(s). Manifest: {manifest_path.as_posix()}")


if __name__ == "__main__":
    main()
