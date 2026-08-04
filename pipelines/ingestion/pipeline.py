from __future__ import annotations

import csv
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from pipelines.ingestion.chunking import chunk_article
from pipelines.ingestion.extractors import get_extractor
from pipelines.ingestion.models import (
    ArticlePipelineResult,
    ExtractionContext,
    PipelineConfig,
)
from pipelines.ingestion.non_instruct import NonInstructPipelineConfig, RelationScoringConfig
from pipelines.ingestion.neo4j_loader import load_processed_record
from pipelines.ingestion.pmc_bioc import BioCUnavailableError, fetch_pmc_bioc, parse_bioc_payload
from pipelines.ingestion.validation import validate_extraction_output


MANIFEST_FIELDNAMES = [
    "pmcid",
    "pmid",
    "title",
    "source_url",
    "raw_path",
    "text_path",
    "processed_path",
    "chunk_count",
    "entity_count",
    "relationship_count",
    "fetch_status",
    "extract_status",
    "load_status",
    "extractor_model",
    "status",
    "error",
]


def ensure_output_directories(output_root: Path, clean_output: bool = False) -> tuple[Path, Path, Path]:
    raw_dir = output_root / "raw"
    text_dir = output_root / "text"
    processed_dir = output_root / "processed"
    if clean_output and output_root.exists():
        shutil.rmtree(output_root)
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, text_dir, processed_dir


def _write_manifest(output_root: Path, results: list[ArticlePipelineResult]) -> None:
    manifest_path = output_root / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows([result.manifest_row() for result in results])


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item.get("id")
        if item_id:
            deduped[str(item_id)] = item
    return list(deduped.values())


def _extractor_model_name(config: PipelineConfig) -> str:
    if config.extractor_provider in {"gliner_ollama", "gliner-ollama"}:
        return f"{config.entity_model} + {config.model}"
    if config.extractor_provider in {"gliner", "gliner_ner", "gliner-ner"}:
        return config.entity_model or config.model
    if config.extractor_provider in {"non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic"}:
        return f"{config.entity_model} + {config.model}"
    return config.model


def build_processed_record(
    run_id: str,
    config: PipelineConfig,
    article: Any,
    chunks: list[dict[str, Any]],
    raw_extractions: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run": {
            "id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source": "pmc_bioc",
            "model_profile": config.model_profile,
            "extractor_provider": config.extractor_provider,
            "extractor_model": _extractor_model_name(config),
            "entity_model": (
                config.entity_model
                if config.extractor_provider in {
                    "gliner_ollama", "gliner-ollama", "gliner", "gliner_ner", "gliner-ner",
                    "non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic",
                }
                else ""
            ),
            "prompt_version": "001_initial_prompt",
            "min_confidence": config.min_confidence,
            "non_instruct_config": {
                "embedding_model": config.embedding_model,
                "terminology_path": config.terminology_path.as_posix() if config.terminology_path else "",
                "entity_threshold": config.entity_threshold,
                "concept_threshold": config.concept_threshold,
                "relation_threshold": config.relation_threshold,
                "semantic_floor": config.semantic_floor,
                "semantic_weight": config.semantic_weight,
                "cue_weight": config.cue_weight,
                "proximity_weight": config.proximity_weight,
                "entity_confidence_weight": config.entity_confidence_weight,
                "max_pair_distance": config.max_pair_distance,
            },
        },
        "document": article.document,
        "chunks": chunks,
        "extractions": raw_extractions,
        "entities": _dedupe(entities),
        "relationships": _dedupe(relationships),
        "rejected_candidates": rejected_candidates,
    }


PipelineProgressCallback = Callable[[dict[str, Any]], None]


def process_pmc_articles(
    config: PipelineConfig,
    progress_callback: PipelineProgressCallback | None = None,
) -> list[ArticlePipelineResult]:
    pmcids = config.pmcids[: config.limit] if config.limit is not None else config.pmcids
    raw_dir, text_dir, processed_dir = ensure_output_directories(config.output_root, config.clean_output)
    non_instruct_config = NonInstructPipelineConfig(
        embedding_model=config.embedding_model or config.model,
        terminology_path=config.terminology_path,
        entity_threshold=config.entity_threshold,
        concept_threshold=config.concept_threshold,
        relation_scoring=RelationScoringConfig(
            relation_threshold=config.relation_threshold,
            semantic_floor=config.semantic_floor,
            semantic_weight=config.semantic_weight,
            cue_weight=config.cue_weight,
            proximity_weight=config.proximity_weight,
            entity_confidence_weight=config.entity_confidence_weight,
            max_pair_distance=config.max_pair_distance,
        ),
    )
    extractor = (
        None
        if config.skip_extract
        else get_extractor(
            config.extractor_provider,
            config.model,
            config.entity_model,
            config.model_call_root,
            entity_threshold=(
                config.entity_threshold
                if config.extractor_provider in {
                    "gliner_ollama", "gliner-ollama", "gliner", "gliner_ner", "gliner-ner",
                    "non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic",
                }
                else None
            ),
            non_instruct_config=(
                non_instruct_config
                if config.extractor_provider in {"non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic"}
                else None
            ),
        )
    )
    run_id = datetime.now(UTC).strftime("pmc-%Y%m%d%H%M%S")
    results: list[ArticlePipelineResult] = []

    if config.apply_schema and not config.skip_load:
        from scripts.apply_neo4j_schema import apply_neo4j_schema

        apply_neo4j_schema()

    for pmcid in pmcids:
        if progress_callback is not None:
            progress_callback({"event": "article_started", "pmcid": pmcid})
        raw_path = raw_dir / f"{pmcid}.json"
        text_path = text_dir / f"{pmcid}.txt"
        processed_path = processed_dir / f"{pmcid}.json"
        result = ArticlePipelineResult(
            pmcid=pmcid,
            pmid="",
            title="",
            raw_path=raw_path,
            text_path=text_path,
            processed_path=processed_path,
            extractor_model=(extractor.model if extractor is not None else ""),
            source_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
        )
        try:
            bioc_payload = fetch_pmc_bioc(pmcid)
            raw_path.write_text(json.dumps(bioc_payload, indent=2), encoding="utf-8")
            article = parse_bioc_payload(bioc_payload, pmcid)
            chunks = chunk_article(article, config.chunk_max_chars, config.chunk_overlap_chars)
            article.document["chunk_count"] = len(chunks)
            article.document["ingested_at"] = datetime.now(UTC).isoformat()
            chunk_payloads = [chunk.to_dict() for chunk in chunks]
            text_path.write_text(article.full_text, encoding="utf-8")

            result.fetch_status = "ok"
            result.pmid = str(article.document.get("pmid") or "")
            result.title = str(article.document.get("title") or "")
            result.chunk_count = len(chunks)

            raw_extractions: list[dict[str, Any]] = []
            entities: list[dict[str, Any]] = []
            relationships: list[dict[str, Any]] = []
            rejected_candidates: list[dict[str, Any]] = []
            chunk_errors: list[str] = []

            if extractor is None:
                result.extract_status = "skipped"
            else:
                result.extract_status = "ok"
                for chunk in chunks:
                    context = ExtractionContext(
                        extractor=extractor.provider,
                        model=extractor.model,
                        min_confidence=config.min_confidence,
                        created_at=datetime.now(UTC).isoformat(),
                    )
                    extraction_record: dict[str, Any] = {
                        "chunk_id": chunk.id,
                        "status": "pending",
                        "entities": [],
                        "relationships": [],
                        "rejected_candidates": [],
                    }
                    try:
                        raw_output = extractor.extract(article.document, chunk)
                        model_call_paths = list(getattr(extractor, "last_model_call_paths", []))
                        normalized = validate_extraction_output(raw_output, article.document, chunk, context)
                        extraction_record.update(
                            {
                                "status": "ok",
                                "entities": normalized["entities"],
                                "relationships": normalized["relationships"],
                                "rejected_candidates": normalized["rejected_candidates"],
                            }
                        )
                        if model_call_paths:
                            extraction_record["model_call_paths"] = model_call_paths
                        entities.extend(normalized["entities"])
                        relationships.extend(normalized["relationships"])
                        rejected_candidates.extend(normalized["rejected_candidates"])
                    except Exception as exc:  # noqa: BLE001
                        extraction_record.update({"status": "error", "error": str(exc)})
                        chunk_errors.append(f"{chunk.id}: {exc}")
                        model_call_paths = list(getattr(extractor, "last_model_call_paths", []))
                        if model_call_paths:
                            extraction_record["model_call_paths"] = model_call_paths
                        result.extract_status = "error"
                        if config.fail_fast:
                            raise
                    raw_extractions.append(extraction_record)

            if chunk_errors:
                result.error = f"{len(chunk_errors)} chunk(s) failed; first error: {chunk_errors[0]}"

            processed_record = build_processed_record(
                run_id=run_id,
                config=config,
                article=article,
                chunks=chunk_payloads,
                raw_extractions=raw_extractions,
                entities=entities,
                relationships=relationships,
                rejected_candidates=rejected_candidates,
            )
            processed_path.write_text(json.dumps(processed_record, indent=2), encoding="utf-8")

            result.entity_count = len(processed_record["entities"])
            result.relationship_count = len(processed_record["relationships"])
            if config.skip_load:
                result.load_status = "skipped"
            else:
                load_processed_record(processed_record)
                result.load_status = "ok"

            result.status = "ok" if result.extract_status != "error" and result.load_status != "error" else "error"
        except BioCUnavailableError as exc:
            result.fetch_status = "skipped"
            result.extract_status = "skipped"
            result.load_status = "skipped"
            result.status = "skipped"
            result.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            result.error = str(exc)
            if result.fetch_status == "pending":
                result.fetch_status = "error"
            if result.extract_status == "pending":
                result.extract_status = "error"
            if result.load_status == "pending":
                result.load_status = "error"
            result.status = "error"
            if config.fail_fast:
                results.append(result)
                _write_manifest(config.output_root, results)
                raise

        results.append(result)
        _write_manifest(config.output_root, results)
        if progress_callback is not None:
            progress_callback({"event": "article_finished", "pmcid": pmcid, "result": result})

    return results
