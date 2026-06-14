from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace

from packages.llm.models import DEFAULT_FRONTIER_MODEL


DEFAULT_MODEL_PROFILE = "frontier"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b-instruct"
DEFAULT_QWEN3_MODEL = "qwen3:8b"
DEFAULT_GLINER_BIOMED_MODEL = "Ihor/gliner-biomed-small-v1.0"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    name: str
    label: str
    description: str
    qa_provider: str
    qa_model: str
    qa_retriever: str
    extractor_provider: str
    extractor_model: str
    entity_model: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


_PROFILES: dict[str, ModelProfile] = {
    "frontier": ModelProfile(
        name="frontier",
        label="Frontier API",
        description="Use the configured OpenAI frontier model for extraction and QA.",
        qa_provider="openai",
        qa_model=DEFAULT_FRONTIER_MODEL,
        qa_retriever="graph",
        extractor_provider="openai",
        extractor_model=DEFAULT_FRONTIER_MODEL,
    ),
    "local-qwen25": ModelProfile(
        name="local-qwen25",
        label="Local Qwen 2.5",
        description="Use Ollama qwen2.5:7b-instruct for QA and GLiNER-BioMed plus Qwen for extraction.",
        qa_provider="ollama",
        qa_model=DEFAULT_OLLAMA_MODEL,
        qa_retriever="graph",
        extractor_provider="gliner_ollama",
        extractor_model=DEFAULT_OLLAMA_MODEL,
        entity_model=DEFAULT_GLINER_BIOMED_MODEL,
    ),
    "local-qwen3": ModelProfile(
        name="local-qwen3",
        label="Local Qwen 3",
        description="Use Ollama qwen3:8b for QA and GLiNER-BioMed plus Qwen for extraction.",
        qa_provider="ollama",
        qa_model=DEFAULT_QWEN3_MODEL,
        qa_retriever="graph",
        extractor_provider="gliner_ollama",
        extractor_model=DEFAULT_QWEN3_MODEL,
        entity_model=DEFAULT_GLINER_BIOMED_MODEL,
    ),
    "noop": ModelProfile(
        name="noop",
        label="Noop smoke test",
        description="Use deterministic local fixtures for plumbing tests without external services.",
        qa_provider="noop",
        qa_model="noop-language-model-v0",
        qa_retriever="noop",
        extractor_provider="noop",
        extractor_model="noop-extractor-v0",
    ),
}

_ALIASES = {
    "local": "local-qwen25",
    "qwen25": "local-qwen25",
    "qwen2.5": "local-qwen25",
    "qwen3": "local-qwen3",
    "openai": "frontier",
    "api": "frontier",
    "none": "noop",
}


def normalize_model_profile_name(name: str | None = None) -> str:
    raw = (name or os.getenv("MODEL_PROFILE") or DEFAULT_MODEL_PROFILE).strip().lower()
    normalized = _ALIASES.get(raw, raw)
    if normalized not in _PROFILES:
        supported = ", ".join(sorted(_PROFILES))
        raise ValueError(f"Unsupported model profile: {name}. Supported profiles: {supported}")
    return normalized


def list_model_profiles() -> list[ModelProfile]:
    return [_PROFILES[name] for name in ("frontier", "local-qwen25", "local-qwen3", "noop")]


def resolve_model_profile(
    name: str | None = None,
    *,
    qa_provider: str | None = None,
    qa_model: str | None = None,
    qa_retriever: str | None = None,
    extractor_provider: str | None = None,
    extractor_model: str | None = None,
    entity_model: str | None = None,
) -> ModelProfile:
    explicit_profile = bool(name and name.strip())
    profile = _PROFILES[normalize_model_profile_name(name)]

    env_qa_provider = None if explicit_profile else os.getenv("QA_PROVIDER") or None
    env_qa_model = None if explicit_profile else os.getenv("QA_MODEL") or None
    env_retriever = None if explicit_profile else os.getenv("QA_RETRIEVER") or None
    env_extractor_provider = None if explicit_profile else os.getenv("EXTRACTOR_PROVIDER") or None
    env_extractor_model = None if explicit_profile else os.getenv("EXTRACTOR_MODEL") or None
    env_entity_model = None if explicit_profile else os.getenv("EXTRACTOR_ENTITY_MODEL") or None
    local_model = None if explicit_profile else os.getenv("LOCAL_MODEL") or None
    openai_model = os.getenv("OPENAI_MODEL") or None

    default_qa_model = profile.qa_model
    default_extractor_model = profile.extractor_model
    if profile.qa_provider == "openai":
        default_qa_model = openai_model or default_qa_model
    elif profile.qa_provider == "ollama":
        default_qa_model = local_model or default_qa_model
    if profile.extractor_provider == "openai":
        default_extractor_model = openai_model or default_extractor_model
    elif profile.extractor_provider == "gliner_ollama":
        default_extractor_model = local_model or default_extractor_model

    resolved_qa_provider = qa_provider or env_qa_provider or profile.qa_provider
    resolved_qa_model = qa_model or env_qa_model or default_qa_model
    resolved_qa_retriever = qa_retriever or env_retriever or profile.qa_retriever
    resolved_extractor_provider = extractor_provider or env_extractor_provider or profile.extractor_provider
    resolved_extractor_model = extractor_model or env_extractor_model or default_extractor_model
    resolved_entity_model = entity_model or env_entity_model or profile.entity_model

    if qa_model is None and env_qa_model is None:
        normalized_qa_provider = resolved_qa_provider.lower().strip()
        if normalized_qa_provider in {"noop", "none"}:
            resolved_qa_model = _PROFILES["noop"].qa_model
        elif normalized_qa_provider == "ollama" and profile.qa_provider != "ollama":
            resolved_qa_model = local_model or DEFAULT_OLLAMA_MODEL
        elif normalized_qa_provider == "local":
            resolved_qa_model = local_model or "local-model"
        elif normalized_qa_provider in {"openai", "fine_tuned", "fine-tuned", "finetuned"}:
            resolved_qa_model = openai_model or DEFAULT_FRONTIER_MODEL

    if extractor_model is None and env_extractor_model is None:
        normalized_extractor_provider = resolved_extractor_provider.lower().strip()
        if normalized_extractor_provider in {"noop", "none"}:
            resolved_extractor_model = _PROFILES["noop"].extractor_model
        elif normalized_extractor_provider in {"gliner_ollama", "gliner-ollama"} and profile.extractor_provider != "gliner_ollama":
            resolved_extractor_model = local_model or DEFAULT_OLLAMA_MODEL
            resolved_entity_model = resolved_entity_model or DEFAULT_GLINER_BIOMED_MODEL
        elif normalized_extractor_provider == "openai":
            resolved_extractor_model = openai_model or DEFAULT_FRONTIER_MODEL

    return replace(
        profile,
        qa_provider=resolved_qa_provider,
        qa_model=resolved_qa_model,
        qa_retriever=resolved_qa_retriever,
        extractor_provider=resolved_extractor_provider,
        extractor_model=resolved_extractor_model,
        entity_model=resolved_entity_model,
    )


def default_model_profile_name() -> str:
    return normalize_model_profile_name()


__all__ = [
    "DEFAULT_GLINER_BIOMED_MODEL",
    "DEFAULT_MODEL_PROFILE",
    "DEFAULT_OLLAMA_MODEL",
    "DEFAULT_QWEN3_MODEL",
    "ModelProfile",
    "default_model_profile_name",
    "list_model_profiles",
    "normalize_model_profile_name",
    "resolve_model_profile",
]
