from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from packages.llm.models import DEFAULT_FRONTIER_MODEL
from packages.llm.profiles import DEFAULT_MODEL_PROFILE


DEFAULT_OUTPUT_ROOT = Path("data/source_documents/pmc_v001")
DEFAULT_CHUNK_MAX_CHARS = 6000
DEFAULT_CHUNK_OVERLAP_CHARS = 500
DEFAULT_PROMPT_VERSION = "001_initial_prompt"
DEFAULT_EXTRACTOR_PROVIDER = "openai"
DEFAULT_OPENAI_MODEL = DEFAULT_FRONTIER_MODEL


@dataclass(slots=True)
class PassageRecord:
    order: int
    section: str
    type: str
    source_offset: int | None
    char_start: int
    char_end: int
    text: str


@dataclass(slots=True)
class ParsedArticle:
    document: dict[str, Any]
    passages: list[PassageRecord]
    full_text: str


@dataclass(slots=True)
class ChunkRecord:
    id: str
    document_id: str
    pmcid: str
    order: int
    char_start: int
    char_end: int
    section: str
    type: str
    source_sections: list[str]
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineConfig:
    pmcids: list[str]
    output_root: Path = DEFAULT_OUTPUT_ROOT
    clean_output: bool = False
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS
    model_profile: str = DEFAULT_MODEL_PROFILE
    extractor_provider: str = DEFAULT_EXTRACTOR_PROVIDER
    model: str = DEFAULT_OPENAI_MODEL
    entity_model: str = ""
    min_confidence: float = 0.5
    apply_schema: bool = False
    skip_extract: bool = False
    skip_load: bool = False
    force: bool = False
    fail_fast: bool = False
    limit: int | None = None
    model_call_root: Path | None = None


@dataclass(slots=True)
class ArticlePipelineResult:
    pmcid: str
    pmid: str
    title: str
    raw_path: Path
    text_path: Path
    processed_path: Path
    chunk_count: int = 0
    entity_count: int = 0
    relationship_count: int = 0
    fetch_status: str = "pending"
    extract_status: str = "pending"
    load_status: str = "pending"
    error: str = ""
    status: str = "pending"
    extractor_model: str = ""

    def manifest_row(self) -> dict[str, Any]:
        return {
            "pmcid": self.pmcid,
            "pmid": self.pmid,
            "title": self.title,
            "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{self.pmcid}/",
            "raw_path": self.raw_path.as_posix(),
            "text_path": self.text_path.as_posix(),
            "processed_path": self.processed_path.as_posix(),
            "chunk_count": self.chunk_count,
            "entity_count": self.entity_count,
            "relationship_count": self.relationship_count,
            "fetch_status": self.fetch_status,
            "extract_status": self.extract_status,
            "load_status": self.load_status,
            "extractor_model": self.extractor_model,
            "status": self.status,
            "error": self.error,
        }


@dataclass(slots=True)
class ExtractionContext:
    extractor: str
    model: str
    prompt_version: str = DEFAULT_PROMPT_VERSION
    min_confidence: float = 0.5
    created_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
