from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pipelines.annotation.review_workbook import ReviewWorkbook
from pipelines.annotation.workbook import ALLOWED_VALUES


UNRESOLVED_STATUSES = {"", "draft", "needs_review", None}
ACCEPTED_STATUS = "accepted"
REJECTED_STATUS = "rejected"
INCLUDE_DECISION = "include"
NEEDS_REVIEW_DECISION = "needs_review"


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    sheet: str
    row_number: int | None
    chunk_id: str
    field: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "summary": self.summary,
        }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm(value: Any) -> str:
    return _clean(value).casefold()


def _row_number(row: dict[str, Any]) -> int | None:
    value = row.get("_row_number")
    return int(value) if isinstance(value, int) else None


def _issue(
    severity: str,
    sheet: str,
    row: dict[str, Any] | None,
    field: str,
    message: str,
    *,
    chunk_id: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        sheet=sheet,
        row_number=_row_number(row or {}),
        chunk_id=chunk_id if chunk_id is not None else _clean((row or {}).get("chunk_id")),
        field=field,
        message=message,
    )


def _is_status_unresolved(row: dict[str, Any]) -> bool:
    return _clean(row.get("annotation_status")) in UNRESOLVED_STATUSES


def _is_entity_accepted(row: dict[str, Any]) -> bool:
    return _clean(row.get("annotation_status")) == ACCEPTED_STATUS


def _is_relationship_accepted(row: dict[str, Any]) -> bool:
    return _clean(row.get("annotation_status")) == ACCEPTED_STATUS and _clean(row.get("annotation_decision")) == INCLUDE_DECISION


def _chunk_by_id(review: ReviewWorkbook) -> dict[str, dict[str, Any]]:
    return {_clean(row.get("chunk_id")): row for row in review.chunks if _clean(row.get("chunk_id"))}


def _accepted_entities_by_chunk(review: ReviewWorkbook) -> dict[str, dict[str, set[str]]]:
    accepted: dict[str, dict[str, set[str]]] = {}
    for row in review.gold_entities:
        if not _is_entity_accepted(row):
            continue
        chunk_id = _clean(row.get("chunk_id"))
        bucket = accepted.setdefault(chunk_id, {"ids": set(), "text_keys": set(), "normalized_keys": set()})
        entity_id = _clean(row.get("entity_id"))
        entity_type = _clean(row.get("entity_type"))
        entity_text = _clean(row.get("entity_text"))
        normalized_name = _clean(row.get("normalized_name")) or entity_text
        if entity_id:
            bucket["ids"].add(entity_id)
        if entity_type and entity_text:
            bucket["text_keys"].add(f"{_norm(entity_type)}|{_norm(entity_text)}")
        if entity_type and normalized_name:
            bucket["normalized_keys"].add(f"{_norm(entity_type)}|{_norm(normalized_name)}")
    return accepted


def _endpoint_is_accepted(
    accepted_entities: dict[str, dict[str, set[str]]],
    chunk_id: str,
    entity_id: Any,
    entity_type: Any,
    entity_text: Any,
    normalized_name: Any,
) -> bool:
    bucket = accepted_entities.get(chunk_id)
    if not bucket:
        return False
    clean_id = _clean(entity_id)
    if clean_id and clean_id in bucket["ids"]:
        return True
    clean_type = _clean(entity_type)
    clean_text = _clean(entity_text)
    clean_normalized = _clean(normalized_name) or clean_text
    text_key = f"{_norm(clean_type)}|{_norm(clean_text)}"
    normalized_key = f"{_norm(clean_type)}|{_norm(clean_normalized)}"
    return text_key in bucket["text_keys"] or normalized_key in bucket["normalized_keys"]


def _offset_evidence_matches(row: dict[str, Any], chunk: dict[str, Any]) -> bool:
    evidence = _clean(row.get("evidence_text"))
    chunk_text = _clean(chunk.get("chunk_text"))
    if not evidence or not chunk_text:
        return False

    start_value = row.get("evidence_start_char")
    end_value = row.get("evidence_end_char")
    chunk_start_value = chunk.get("start_char")
    try:
        start = int(start_value)
        end = int(end_value)
        chunk_start = int(chunk_start_value or 0)
    except (TypeError, ValueError):
        return False

    local_start = start - chunk_start
    local_end = end - chunk_start
    if local_start < 0 or local_end < local_start or local_end > len(chunk_text):
        return False
    return chunk_text[local_start:local_end].casefold() == evidence.casefold()


def _evidence_is_supported(row: dict[str, Any], chunk: dict[str, Any]) -> bool:
    evidence = _clean(row.get("evidence_text"))
    chunk_text = _clean(chunk.get("chunk_text"))
    if not evidence or not chunk_text:
        return False
    return evidence.casefold() in chunk_text.casefold() or _offset_evidence_matches(row, chunk)


def _validate_chunks(review: ReviewWorkbook, errors: list[ValidationIssue]) -> None:
    seen: set[str] = set()
    for row in review.chunks:
        chunk_id = _clean(row.get("chunk_id"))
        if not chunk_id:
            errors.append(_issue("error", "chunks", row, "chunk_id", "Chunk row is missing chunk_id."))
            continue
        if chunk_id in seen:
            errors.append(_issue("error", "chunks", row, "chunk_id", "Duplicate chunk_id in chunks sheet."))
        seen.add(chunk_id)
        if _is_status_unresolved(row):
            errors.append(
                _issue(
                    "error",
                    "chunks",
                    row,
                    "annotation_status",
                    "Chunk is still unresolved; mark reviewed or accepted before gold export.",
                )
            )


def _validate_entities(review: ReviewWorkbook, chunks: dict[str, dict[str, Any]], errors: list[ValidationIssue]) -> None:
    allowed_entity_types = set(ALLOWED_VALUES["entity_type"])
    for row in review.gold_entities:
        if _is_status_unresolved(row):
            errors.append(
                _issue(
                    "error",
                    "gold_entities",
                    row,
                    "annotation_status",
                    "Entity row is still unresolved.",
                )
            )
            continue
        if not _is_entity_accepted(row):
            continue

        entity_type = _clean(row.get("entity_type"))
        if entity_type not in allowed_entity_types:
            errors.append(_issue("error", "gold_entities", row, "entity_type", f"Invalid entity type: {entity_type}"))
        if not _clean(row.get("entity_text")):
            errors.append(_issue("error", "gold_entities", row, "entity_text", "Accepted entity is missing entity_text."))
        chunk = chunks.get(_clean(row.get("chunk_id")))
        if not chunk:
            errors.append(_issue("error", "gold_entities", row, "chunk_id", "Accepted entity references an unknown chunk."))
        elif not _evidence_is_supported(row, chunk):
            errors.append(
                _issue(
                    "error",
                    "gold_entities",
                    row,
                    "evidence_text",
                    "Accepted entity evidence_text or offsets do not match the chunk text.",
                )
            )


def _validate_relationships(
    review: ReviewWorkbook,
    chunks: dict[str, dict[str, Any]],
    accepted_entities: dict[str, dict[str, set[str]]],
    errors: list[ValidationIssue],
) -> None:
    allowed_relationship_types = set(ALLOWED_VALUES["relationship_type"])
    for row in review.gold_relationships:
        status = _clean(row.get("annotation_status"))
        decision = _clean(row.get("annotation_decision"))
        if status in UNRESOLVED_STATUSES or decision in {"", NEEDS_REVIEW_DECISION}:
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "annotation_decision",
                    "Relationship row is still unresolved.",
                )
            )
            continue
        if not _is_relationship_accepted(row):
            continue

        relationship_type = _clean(row.get("relationship_type"))
        if relationship_type not in allowed_relationship_types:
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "relationship_type",
                    f"Invalid relationship type: {relationship_type}",
                )
            )

        chunk_id = _clean(row.get("chunk_id"))
        chunk = chunks.get(chunk_id)
        if not chunk:
            errors.append(_issue("error", "gold_relationships", row, "chunk_id", "Accepted relationship references an unknown chunk."))
        elif not _evidence_is_supported(row, chunk):
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "evidence_text",
                    "Accepted relationship evidence_text or offsets do not match the chunk text.",
                )
            )

        if _clean(row.get("direction_verified")) != "yes":
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "direction_verified",
                    "Accepted relationship must have direction_verified=yes.",
                )
            )
        if _clean(row.get("negated")) != "no":
            errors.append(_issue("error", "gold_relationships", row, "negated", "Accepted relationship must have negated=no."))
        if _clean(row.get("speculative")) != "no":
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "speculative",
                    "Accepted relationship must have speculative=no.",
                )
            )
        if _clean(row.get("explicit_or_implied")) == "weak_implication":
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "explicit_or_implied",
                    "Weakly implied relationships are not exported to the core gold set.",
                )
            )

        source_ok = _endpoint_is_accepted(
            accepted_entities,
            chunk_id,
            row.get("source_entity_id"),
            row.get("source_entity_type"),
            row.get("source_entity_text"),
            row.get("source_normalized_name"),
        )
        target_ok = _endpoint_is_accepted(
            accepted_entities,
            chunk_id,
            row.get("target_entity_id"),
            row.get("target_entity_type"),
            row.get("target_entity_text"),
            row.get("target_normalized_name"),
        )
        if not source_ok:
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "source_entity_id",
                    "Accepted relationship source endpoint does not map to an accepted entity in the same chunk.",
                )
            )
        if not target_ok:
            errors.append(
                _issue(
                    "error",
                    "gold_relationships",
                    row,
                    "target_entity_id",
                    "Accepted relationship target endpoint does not map to an accepted entity in the same chunk.",
                )
            )


def validate_review_workbook(review: ReviewWorkbook) -> ValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    chunks = _chunk_by_id(review)
    accepted_entities = _accepted_entities_by_chunk(review)

    _validate_chunks(review, errors)
    _validate_entities(review, chunks, errors)
    _validate_relationships(review, chunks, accepted_entities, errors)

    summary = {
        "document_count": len(review.documents),
        "chunk_count": len(review.chunks),
        "entity_rows": len(review.gold_entities),
        "relationship_rows": len(review.gold_relationships),
        "accepted_entities": sum(1 for row in review.gold_entities if _is_entity_accepted(row)),
        "accepted_relationships": sum(1 for row in review.gold_relationships if _is_relationship_accepted(row)),
        "rejected_entities": sum(1 for row in review.gold_entities if _clean(row.get("annotation_status")) == REJECTED_STATUS),
        "rejected_relationships": sum(
            1
            for row in review.gold_relationships
            if _clean(row.get("annotation_status")) == REJECTED_STATUS or _clean(row.get("annotation_decision")) == "exclude"
        ),
        "unresolved_entities": sum(1 for row in review.gold_entities if _is_status_unresolved(row)),
        "unresolved_relationships": sum(
            1
            for row in review.gold_relationships
            if _clean(row.get("annotation_status")) in UNRESOLVED_STATUSES
            or _clean(row.get("annotation_decision")) in {"", NEEDS_REVIEW_DECISION}
        ),
    }
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings, summary=summary)


__all__ = [
    "ACCEPTED_STATUS",
    "INCLUDE_DECISION",
    "ValidationIssue",
    "ValidationResult",
    "validate_review_workbook",
]
