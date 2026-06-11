from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.ingestion.pmc_bioc import parse_bioc_payload


DEFAULT_OUTPUT_ROOT = Path("data/source_documents/pmc_v001")
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200


@dataclass
class ChunkRecord:
	id: str
	document_id: str
	order: int
	char_start: int
	char_end: int
	text: str


@dataclass
class IngestionRecord:
	document: dict[str, Any]
	chunks: list[ChunkRecord]
	relations: list[dict[str, Any]]


def normalize_pmcid(pmcid: str) -> str:
	cleaned = pmcid.strip().upper()
	if not cleaned:
		raise ValueError("PMCID cannot be empty")
	if not cleaned.startswith("PMC"):
		cleaned = f"PMC{cleaned}"
	if not re.fullmatch(r"PMC\d+", cleaned):
		raise ValueError(f"Invalid PMCID format: {pmcid}")
	return cleaned


def get_pmc_bioc_urls(pmcid: str) -> list[str]:
	encoded = parse.quote(pmcid)
	return [
		f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{encoded}/unicode",
		f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{encoded}/ascii",
	]


def fetch_pmc_bioc(pmcid: str, timeout_seconds: int = 45) -> dict[str, Any]:
	last_error: Exception | None = None
	for url in get_pmc_bioc_urls(pmcid):
		try:
			req = request.Request(url, headers={"User-Agent": "med-graph-rag-ingestion/0.1"})
			with request.urlopen(req, timeout=timeout_seconds) as response:
				payload = response.read().decode("utf-8")
				return json.loads(payload)
			print(f"Fetched BioC JSON for {pmcid} from {url}")
		except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
			last_error = exc
			print(f"Warning: Failed to fetch BioC JSON for {pmcid} from {url}: {exc}")
			continue

	raise RuntimeError(f"Failed to fetch BioC JSON for {pmcid}: {last_error}")


def clean_text(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[tuple[int, int, str]]:
	if chunk_size <= 0:
		raise ValueError("chunk_size must be positive")
	if overlap < 0:
		raise ValueError("overlap cannot be negative")
	if overlap >= chunk_size:
		raise ValueError("overlap must be smaller than chunk_size")

	chunks: list[tuple[int, int, str]] = []
	start = 0
	text_length = len(text)

	while start < text_length:
		end = min(start + chunk_size, text_length)
		if end < text_length:
			split_idx = text.rfind(" ", start, end)
			if split_idx > start + int(chunk_size * 0.6):
				end = split_idx

		chunk = text[start:end].strip()
		if chunk:
			chunks.append((start, end, chunk))

		if end >= text_length:
			break
		start = max(end - overlap, start + 1)

	return chunks


def extract_document_fields(bioc_payload: Any, pmcid: str) -> tuple[str, str | None, str]:
	article = parse_bioc_payload(bioc_payload, pmcid)
	return article.document["title"], article.document.get("pmid") or None, article.full_text


def ensure_output_directories(output_root: Path, clean_output_dir: bool) -> tuple[Path, Path, Path]:
	raw_dir = output_root / "raw"
	text_dir = output_root / "text"
	processed_dir = output_root / "processed"

	if clean_output_dir and output_root.exists():
		shutil.rmtree(output_root)

	raw_dir.mkdir(parents=True, exist_ok=True)
	text_dir.mkdir(parents=True, exist_ok=True)
	processed_dir.mkdir(parents=True, exist_ok=True)

	return raw_dir, text_dir, processed_dir


def build_ingestion_record(
	pmcid: str,
	pmid: str | None,
	title: str,
	full_text: str,
	chunk_size: int,
	chunk_overlap: int,
) -> IngestionRecord:
	chunk_spans = chunk_text(full_text, chunk_size=chunk_size, overlap=chunk_overlap)
	chunks: list[ChunkRecord] = []

	for idx, (start, end, chunk_value) in enumerate(chunk_spans, start=1):
		chunks.append(
			ChunkRecord(
				id=f"{pmcid}-chunk-{idx:04d}",
				document_id=pmcid,
				order=idx,
				char_start=start,
				char_end=end,
				text=chunk_value,
			)
		)

	document = {
		"id": pmcid,
		"pmcid": pmcid,
		"pmid": pmid,
		"title": title,
		"source": "pmc",
		"source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
		"text_length": len(full_text),
		"chunk_count": len(chunks),
		"ingested_at": datetime.now(UTC).isoformat(),
	}

	return IngestionRecord(document=document, chunks=chunks, relations=[])


def fetch_and_chunk_pmc_articles(
	pmcids: list[str],
	output_root: Path = DEFAULT_OUTPUT_ROOT,
	clean_output_dir: bool = False,
	chunk_size: int = DEFAULT_CHUNK_SIZE,
	chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestionRecord]:
	normalized_ids = [normalize_pmcid(pmcid) for pmcid in pmcids]
	raw_dir, text_dir, processed_dir = ensure_output_directories(output_root, clean_output_dir)

	manifest_rows: list[dict[str, Any]] = []
	results: list[IngestionRecord] = []

	for pmcid in normalized_ids:
		source_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
		raw_path = raw_dir / f"{pmcid}.json"
		text_path = text_dir / f"{pmcid}.txt"
		processed_path = processed_dir / f"{pmcid}.json"

		try:
			bioc_payload = fetch_pmc_bioc(pmcid)
			title, pmid, full_text = extract_document_fields(bioc_payload, pmcid)
			if not full_text:
				raise RuntimeError(f"No text passages found for {pmcid}")

			raw_path.write_text(json.dumps(bioc_payload, indent=2), encoding="utf-8")
			text_path.write_text(full_text, encoding="utf-8")

			record = build_ingestion_record(
				pmcid=pmcid,
				pmid=pmid,
				title=title,
				full_text=full_text,
				chunk_size=chunk_size,
				chunk_overlap=chunk_overlap,
			)
			processed_payload = {
				"document": record.document,
				"chunks": [asdict(chunk) for chunk in record.chunks],
				"relations": record.relations,
			}
			processed_path.write_text(json.dumps(processed_payload, indent=2), encoding="utf-8")

			results.append(record)
			manifest_rows.append(
				{
					"pmcid": pmcid,
					"pmid": pmid or "",
					"title": title,
					"source_url": source_url,
					"raw_path": raw_path.as_posix(),
					"text_path": text_path.as_posix(),
					"processed_path": processed_path.as_posix(),
					"chunk_count": len(record.chunks),
					"status": "ok",
					"error": "",
				}
			)
		except Exception as exc:  # noqa: BLE001
			manifest_rows.append(
				{
					"pmcid": pmcid,
					"pmid": "",
					"title": "",
					"source_url": source_url,
					"raw_path": raw_path.as_posix(),
					"text_path": text_path.as_posix(),
					"processed_path": processed_path.as_posix(),
					"chunk_count": 0,
					"status": "error",
					"error": str(exc),
				}
			)

	manifest_path = output_root / "manifest.csv"
	with manifest_path.open("w", newline="", encoding="utf-8") as handle:
		fieldnames = [
			"pmcid",
			"pmid",
			"title",
			"source_url",
			"raw_path",
			"text_path",
			"processed_path",
			"chunk_count",
			"status",
			"error",
		]
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(manifest_rows)

	return results


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Fetch PMC BioC JSON and produce chunked ingestion artifacts")
	parser.add_argument(
		"--pmcid",
		action="append",
		nargs="+",
		dest="pmcids",
		required=True,
		help="PMC article id. Can be repeated or space-separated: --pmcid PMC123 PMC456",
	)
	parser.add_argument(
		"--output-root",
		default=str(DEFAULT_OUTPUT_ROOT),
		help="Directory for raw/text/processed artifacts and manifest.csv",
	)
	parser.add_argument("--clean-output", action="store_true", help="Delete output directory before writing artifacts")
	parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
	parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	output_root = Path(args.output_root)
	pmcids = [pmcid for group in args.pmcids for pmcid in group]
	records = fetch_and_chunk_pmc_articles(
		pmcids=pmcids,
		output_root=output_root,
		clean_output_dir=args.clean_output,
		chunk_size=args.chunk_size,
		chunk_overlap=args.chunk_overlap,
	)
	print(f"Fetched {len(records)} article(s). Manifest: {(output_root / 'manifest.csv').as_posix()}")


if __name__ == "__main__":
	main()
