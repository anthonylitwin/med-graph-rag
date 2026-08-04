from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from pipelines.ingestion.chunking import chunk_article
from pipelines.ingestion.extractors import get_extractor
from pipelines.ingestion.models import (
    ArticlePipelineResult,
    ExtractionContext,
    ParsedArticle,
    PassageRecord,
    PipelineConfig,
)
from pipelines.ingestion.neo4j_loader import load_processed_record
from pipelines.ingestion.non_instruct import NonInstructPipelineConfig, RelationScoringConfig
from pipelines.ingestion.pipeline import (
    _write_manifest,
    build_processed_record,
    ensure_output_directories,
)
from pipelines.ingestion.validation import validate_extraction_output


TextProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class TextDocumentInput:
    title: str
    text: str
    source_name: str = ""


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:40] or "document"


def _text_document_key(title: str, text: str) -> str:
    digest = hashlib.sha1(f"{title}\n{text}".encode("utf-8")).hexdigest()[:12]
    return f"TEXT{digest.upper()}"


def _article_from_text(input_document: TextDocumentInput) -> ParsedArticle:
    text = input_document.text.strip()
    if not text:
        raise ValueError("Text document cannot be empty")
    title = input_document.title.strip() or input_document.source_name.strip() or "Uploaded text document"
    document_key = _text_document_key(title, text)
    passage = PassageRecord(
        order=1,
        section="Uploaded text",
        type="text",
        source_offset=None,
        char_start=0,
        char_end=len(text),
        text=text,
    )
    document = {
        "id": f"paper:{document_key}",
        "pmcid": document_key,
        "pmid": "",
        "title": title,
        "year": "",
        "journal": "",
        "doi": "",
        "authors": [],
        "source": "uploaded_text",
        "source_url": "",
        "text_length": len(text),
    }
    return ParsedArticle(document=document, passages=[passage], full_text=text)


def process_text_documents(
    config: PipelineConfig,
    documents: list[TextDocumentInput],
    progress_callback: TextProgressCallback | None = None,
) -> list[ArticlePipelineResult]:
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
                if config.extractor_provider
                in {
                    "gliner_ollama",
                    "gliner-ollama",
                    "gliner",
                    "gliner_ner",
                    "gliner-ner",
                    "non_instruct",
                    "non-instruct",
                    "gliner_semantic",
                    "gliner-semantic",
                }
                else None
            ),
            non_instruct_config=(
                non_instruct_config
                if config.extractor_provider
                in {"non_instruct", "non-instruct", "gliner_semantic", "gliner-semantic"}
                else None
            ),
        )
    )
    run_id = datetime.now(UTC).strftime("text-%Y%m%d%H%M%S")
    results: list[ArticlePipelineResult] = []

    if config.apply_schema and not config.skip_load:
        from scripts.apply_neo4j_schema import apply_neo4j_schema

        apply_neo4j_schema()

    for input_document in documents:
        article = _article_from_text(input_document)
        document_key = str(article.document["pmcid"])
        if progress_callback is not None:
            progress_callback({"event": "article_started", "pmcid": document_key})

        raw_path = raw_dir / f"{document_key}.json"
        text_path = text_dir / f"{document_key}-{_slug(article.document['title'])}.txt"
        processed_path = processed_dir / f"{document_key}.json"
        result = ArticlePipelineResult(
            pmcid=document_key,
            pmid="",
            title=str(article.document["title"]),
            raw_path=raw_path,
            text_path=text_path,
            processed_path=processed_path,
            extractor_model=(extractor.model if extractor is not None else ""),
            source_url="",
        )

        try:
            chunks = chunk_article(article, config.chunk_max_chars, config.chunk_overlap_chars)
            article.document["chunk_count"] = len(chunks)
            article.document["ingested_at"] = datetime.now(UTC).isoformat()
            chunk_payloads = [chunk.to_dict() for chunk in chunks]
            raw_path.write_text(
                json.dumps(
                    {
                        "source": "uploaded_text",
                        "source_name": input_document.source_name,
                        "title": article.document["title"],
                        "document_key": document_key,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            text_path.write_text(article.full_text, encoding="utf-8")

            result.fetch_status = "ok"
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
            progress_callback({"event": "article_finished", "pmcid": document_key, "result": result})

    return results
