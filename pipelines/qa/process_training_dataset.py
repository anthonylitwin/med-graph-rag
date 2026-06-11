from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.qa.datasets import TrainingExample, read_training_dataset, to_openai_finetune_record


MANIFEST_FIELDNAMES = ["example_id", "question", "answer_chars", "evidence_count", "status", "error"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process QA training datasets into fine-tuning artifacts")
    parser.add_argument("--dataset", type=Path, required=True, help="JSON or JSONL training dataset.")
    parser.add_argument("--output-root", type=Path, default=Path("data/training/qa_v001"))
    parser.add_argument("--clean-output", action="store_true", help="Delete output directory before writing artifacts")
    parser.add_argument(
        "--export-format",
        default="openai-jsonl",
        choices=["openai-jsonl", "local-jsonl", "internal-jsonl"],
    )
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def _manifest_row(example: TrainingExample, status: str = "ok", error: str = "") -> dict[str, Any]:
    return {
        "example_id": example.id,
        "question": example.question,
        "answer_chars": len(example.answer),
        "evidence_count": len(example.evidence),
        "status": status,
        "error": error,
    }


def _export_record(example: TrainingExample, export_format: str) -> dict[str, Any]:
    if export_format == "openai-jsonl":
        return to_openai_finetune_record(example)
    if export_format == "local-jsonl":
        return {
            "id": example.id,
            "instruction": example.question,
            "input": {"evidence": example.evidence},
            "output": example.answer,
            "metadata": example.metadata,
        }
    return example.to_dict()


def process_dataset(dataset: Path, output_root: Path, export_format: str, clean_output: bool, limit: int | None) -> Path:
    if clean_output and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    examples = read_training_dataset(dataset, limit)
    suffix = {
        "openai-jsonl": "openai_finetune.jsonl",
        "local-jsonl": "local_sft.jsonl",
        "internal-jsonl": "training_examples.jsonl",
    }[export_format]
    export_path = output_root / suffix
    manifest_path = output_root / "manifest.csv"

    with export_path.open("w", encoding="utf-8") as export_handle, manifest_path.open(
        "w", newline="", encoding="utf-8"
    ) as manifest_handle:
        writer = csv.DictWriter(manifest_handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        for example in examples:
            export_handle.write(json.dumps(_export_record(example, export_format), ensure_ascii=True) + "\n")
            writer.writerow(_manifest_row(example))

    return export_path


def main() -> None:
    args = parse_args()
    export_path = process_dataset(args.dataset, args.output_root, args.export_format, args.clean_output, args.limit)
    print(f"Processed QA training dataset: {export_path.as_posix()}")


if __name__ == "__main__":
    main()
