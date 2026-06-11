from __future__ import annotations

from pipelines.ingestion.models import ChunkRecord, ParsedArticle, PassageRecord


def _split_text_spans(text: str, chunk_max_chars: int, overlap_chars: int) -> list[tuple[int, int]]:
    if chunk_max_chars <= 0:
        raise ValueError("chunk_max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars cannot be negative")
    if overlap_chars >= chunk_max_chars:
        raise ValueError("overlap_chars must be smaller than chunk_max_chars")

    spans: list[tuple[int, int]] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_max_chars, text_length)
        if end < text_length:
            split_idx = text.rfind(" ", start, end)
            if split_idx > start + int(chunk_max_chars * 0.6):
                end = split_idx
        if text[start:end].strip():
            spans.append((start, end))
        if end >= text_length:
            break
        start = max(end - overlap_chars, start + 1)
    return spans


def _overlapping_passages(passages: list[PassageRecord], start: int, end: int) -> list[PassageRecord]:
    return [passage for passage in passages if passage.char_start < end and passage.char_end > start]


def chunk_article(
    article: ParsedArticle,
    chunk_max_chars: int,
    overlap_chars: int,
) -> list[ChunkRecord]:
    pmcid = str(article.document["pmcid"])
    document_id = str(article.document["id"])
    spans = _split_text_spans(article.full_text, chunk_max_chars, overlap_chars)
    chunks: list[ChunkRecord] = []

    for order, (start, end) in enumerate(spans, start=1):
        text = article.full_text[start:end].strip()
        overlaps = _overlapping_passages(article.passages, start, end)
        sections = []
        for passage in overlaps:
            section = passage.section or passage.type
            if section and section not in sections:
                sections.append(section)
        first_passage = overlaps[0] if overlaps else None

        chunks.append(
            ChunkRecord(
                id=f"{pmcid}-chunk-{order:04d}",
                document_id=document_id,
                pmcid=pmcid,
                order=order,
                char_start=start,
                char_end=end,
                section=(first_passage.section if first_passage else "") or "",
                type=(first_passage.type if first_passage else "") or "",
                source_sections=sections,
                text=text,
            )
        )

    return chunks
