from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from typing import Any
from urllib import error, parse, request

from pipelines.ingestion.models import ParsedArticle, PassageRecord
from pipelines.ingestion.pmc_inputs import normalize_pmcid


class BioCUnavailableError(RuntimeError):
    """Raised when NCBI BioC has no JSON document for a valid PMC article."""


RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


def get_pmc_bioc_urls(pmcid: str) -> list[str]:
    encoded = parse.quote(normalize_pmcid(pmcid))
    return [
        f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{encoded}/unicode",
        f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{encoded}/ascii",
    ]


def _is_no_result_response(payload: str) -> bool:
    return payload.lstrip().startswith("[Error]") and "No result can be found" in payload[:200]


def _is_retryable_fetch_error(exc: Exception) -> bool:
    if isinstance(exc, error.HTTPError):
        return exc.code in RETRYABLE_HTTP_STATUS_CODES
    return isinstance(exc, (error.URLError, TimeoutError))


def fetch_pmc_bioc(
    pmcid: str,
    timeout_seconds: int = 45,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 2.0,
) -> Any:
    last_error: Exception | None = None
    unavailable_error: BioCUnavailableError | None = None
    normalized_pmcid = normalize_pmcid(pmcid)
    for url in get_pmc_bioc_urls(pmcid):
        for attempt in range(retry_attempts + 1):
            try:
                req = request.Request(url, headers={"User-Agent": "med-graph-rag-ingestion/0.1"})
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                    content_type = response.headers.get("Content-Type", "")
                    if _is_no_result_response(payload):
                        unavailable_error = BioCUnavailableError(
                            f"BioC JSON unavailable for {normalized_pmcid}: NCBI returned no result"
                        )
                        break
                    if content_type and "json" not in content_type.casefold():
                        last_error = RuntimeError(
                            f"Expected BioC JSON from {url} but got {content_type}; body starts: {payload[:120]!r}"
                        )
                        break
                    return json.loads(payload)
            except (error.HTTPError, error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < retry_attempts and _is_retryable_fetch_error(exc):
                    if retry_delay_seconds > 0:
                        time.sleep(retry_delay_seconds * (2**attempt))
                    continue
                break
            except json.JSONDecodeError as exc:
                last_error = exc
                break

    if unavailable_error is not None:
        raise unavailable_error
    raise RuntimeError(f"Failed to fetch BioC JSON for {pmcid}: {last_error}")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _iter_documents(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        documents = value.get("documents")
        if isinstance(documents, list):
            for document in documents:
                yield from _iter_documents(document)
            return
        if isinstance(value.get("passages"), list):
            yield value
        return

    if isinstance(value, list):
        for item in value:
            yield from _iter_documents(item)


def _first_string(infons: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = infons.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value if str(item).strip())
        text = clean_text(str(value))
        if text:
            return text
    return ""


def _parse_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(str(item)) for item in value if clean_text(str(item))]
    if isinstance(value, str):
        separator = ";" if ";" in value else ","
        return [clean_text(item) for item in value.split(separator) if clean_text(item)]
    return []


def _is_title_passage(infons: dict[str, Any]) -> bool:
    section_type = str(infons.get("section_type", "")).lower()
    type_value = str(infons.get("type", "")).lower()
    return section_type == "title" or type_value == "title"


def parse_bioc_payload(bioc_payload: Any, pmcid: str) -> ParsedArticle:
    normalized_pmcid = normalize_pmcid(pmcid)
    documents = list(_iter_documents(bioc_payload))
    if not documents:
        raise RuntimeError(f"No BioC documents found for {normalized_pmcid}")

    document = documents[0]
    infons = document.get("infons") if isinstance(document.get("infons"), dict) else {}
    passages_payload = document.get("passages") if isinstance(document.get("passages"), list) else []

    title = _first_string(infons, ["article-title", "title"])
    pmid = _first_string(infons, ["article-id_pmid", "pmid", "PMID"])
    doi = _first_string(infons, ["article-id_doi", "doi", "DOI"])
    journal = _first_string(infons, ["journal-title", "journal", "journal_name"])
    year = _first_string(infons, ["year", "pub-year", "publication_year"])
    authors = _parse_authors(infons.get("authors") or infons.get("author"))

    passages: list[PassageRecord] = []
    full_text_parts: list[str] = []
    cursor = 0

    for order, passage in enumerate(passages_payload, start=1):
        if not isinstance(passage, dict):
            continue
        raw_text = clean_text(str(passage.get("text", "")))
        if not raw_text:
            continue

        passage_infons = passage.get("infons") if isinstance(passage.get("infons"), dict) else {}
        section = clean_text(
            str(
                passage_infons.get("section")
                or passage_infons.get("section_type")
                or passage_infons.get("type")
                or ""
            )
        )
        passage_type = clean_text(str(passage_infons.get("type") or passage_infons.get("section_type") or ""))
        source_offset = passage.get("offset")
        if not isinstance(source_offset, int):
            source_offset = None

        if not title and _is_title_passage(passage_infons):
            title = raw_text

        if full_text_parts:
            cursor += 2
        char_start = cursor
        char_end = char_start + len(raw_text)
        cursor = char_end
        full_text_parts.append(raw_text)

        passages.append(
            PassageRecord(
                order=order,
                section=section,
                type=passage_type,
                source_offset=source_offset,
                char_start=char_start,
                char_end=char_end,
                text=raw_text,
            )
        )

    full_text = "\n\n".join(full_text_parts).strip()
    if not full_text:
        raise RuntimeError(f"No text passages found for {normalized_pmcid}")
    if not title:
        title = f"PMC article {normalized_pmcid}"

    article_document = {
        "id": f"paper:{normalized_pmcid}",
        "pmcid": normalized_pmcid,
        "pmid": pmid,
        "title": title,
        "year": year,
        "journal": journal,
        "doi": doi,
        "authors": authors,
        "source": "pmc",
        "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_pmcid}/",
        "text_length": len(full_text),
    }

    return ParsedArticle(document=article_document, passages=passages, full_text=full_text)
