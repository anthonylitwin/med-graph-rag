from __future__ import annotations

import re
from pathlib import Path


PMCID_PATTERN = re.compile(r"^(?:PMC)?\d+$", re.IGNORECASE)


def normalize_pmcid(pmcid: str) -> str:
    cleaned = pmcid.strip().upper()
    if not cleaned:
        raise ValueError("PMCID cannot be empty")
    if not cleaned.startswith("PMC"):
        cleaned = f"PMC{cleaned}"
    if not re.fullmatch(r"PMC\d+", cleaned):
        raise ValueError(f"Invalid PMCID format: {pmcid}")
    return cleaned


def read_pmcid_file(path: Path) -> list[str]:
    pmcids: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not PMCID_PATTERN.fullmatch(line):
            raise ValueError(
                f"{path.as_posix()} line {line_number} is not a plain PMCID: {raw_line!r}"
            )
        pmcids.append(line)
    return pmcids


def flatten_pmcid_args(pmcid_groups: list[list[str]] | None) -> list[str]:
    if not pmcid_groups:
        return []
    flattened: list[str] = []
    for group in pmcid_groups:
        flattened.extend(group)
    return flattened


def collect_pmcids(
    pmcid_groups: list[list[str]] | None = None,
    pmcid_file: Path | None = None,
    limit: int | None = None,
) -> list[str]:
    raw_values = flatten_pmcid_args(pmcid_groups)
    if pmcid_file is not None:
        raw_values.extend(read_pmcid_file(pmcid_file))

    seen: set[str] = set()
    normalized: list[str] = []
    for raw_value in raw_values:
        pmcid = normalize_pmcid(raw_value)
        if pmcid in seen:
            continue
        seen.add(pmcid)
        normalized.append(pmcid)

    if limit is not None:
        if limit < 0:
            raise ValueError("limit cannot be negative")
        normalized = normalized[:limit]

    if not normalized:
        raise ValueError("Provide at least one PMCID with --pmcid or --pmcid-file")

    return normalized
