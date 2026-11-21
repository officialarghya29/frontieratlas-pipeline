"""Typed configuration loading with environment-variable expansion.

Secrets are never stored in YAML. Values may reference environment variables
using ``${VAR}`` or ``${VAR:-default}`` so that the same config works in local
development and CI.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at the top level of {path}")
    return _expand_env(data)


def display_path(path: Path, *, base: Path | None = None) -> str:
    """Return a portable path for exported metadata, never a machine-local absolute path."""

    resolved = Path(path).resolve()
    root = (base or PROJECT_ROOT).resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return resolved.name


@dataclass(frozen=True)
class HttpSettings:
    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0
    max_retries: int = 4
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 45.0
    global_concurrency: int = 8
    per_domain_concurrency: int = 2
    default_min_interval_seconds: float = 0.25
    user_agent: str = "FrontierAtlasBot/1.0"
    rate_limits: dict[str, float] = field(default_factory=dict)

    def min_interval_for(self, host: str) -> float:
        return float(self.rate_limits.get(host, self.default_min_interval_seconds))


@dataclass(frozen=True)
class FreshnessSettings:
    max_age_hours: int = 24
    clock_skew_minutes: int = 5


@dataclass(frozen=True)
class LlmProviderConfig:
    name: str
    api_key_env: str
    model_env: str
    default_model: str
    endpoint: str
    max_input_chars: int = 20000


@dataclass(frozen=True)
class LlmSettings:
    enabled: bool = True
    providers: tuple[LlmProviderConfig, ...] = ()
    request_timeout_seconds: float = 90.0
    max_retries_per_provider: int = 2
    retry_base_seconds: float = 2.0
    retry_max_seconds: float = 30.0
    circuit_break_after_failures: int = 3
    chunk_target_chars: int = 12000
    chunk_overlap_chars: int = 600


@dataclass(frozen=True)
class EntityResolutionSettings:
    exact_threshold: float = 100
    alias_threshold: float = 98
    domain_threshold: float = 95
    auto_merge_threshold: float = 97
    review_threshold: float = 80
    min_auto_length_ratio: float = 0.8
    min_auto_character_ratio: float = 90
    name_max_tokens: int = 5
    name_max_chars: int = 60
    seed_entity_file: str = "config/seed_entities.txt"


@dataclass(frozen=True)
class SheetsSettings:
    spreadsheet_title: str = "FrontierAtlas — AI Ecosystem Dataset"
    tabs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AppSettings:
    http: HttpSettings
    freshness: FreshnessSettings
    llm: LlmSettings
    entity_resolution: EntityResolutionSettings
    sheets: SheetsSettings
    database_path: Path
    raw_dir: Path
    processed_dir: Path
    export_dir: Path
    sources: dict[str, Any]

    def tab_name(self, record_type: str) -> str:
        return self.sheets.tabs.get(record_type, record_type.replace("_", " ").title())


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


@lru_cache(maxsize=4)
def load_settings(root: Path | None = None) -> AppSettings:
    base = Path(root) if root else PROJECT_ROOT
    raw = load_yaml(base / "config" / "settings.yaml")
    sources = load_yaml(base / "config" / "sources.yaml")

    http_raw = dict(raw.get("http", {}))
    http = HttpSettings(
        timeout_seconds=float(http_raw.get("timeout_seconds", 30)),
        connect_timeout_seconds=float(http_raw.get("connect_timeout_seconds", 10)),
        max_retries=int(http_raw.get("max_retries", 4)),
        base_backoff_seconds=float(http_raw.get("base_backoff_seconds", 1.0)),
        max_backoff_seconds=float(http_raw.get("max_backoff_seconds", 45)),
        global_concurrency=int(http_raw.get("global_concurrency", 8)),
        per_domain_concurrency=int(http_raw.get("per_domain_concurrency", 2)),
        default_min_interval_seconds=float(http_raw.get("default_min_interval_seconds", 0.25)),
        user_agent=str(http_raw.get("user_agent", "FrontierAtlasBot/1.0")),
        rate_limits={str(k): float(v) for k, v in (http_raw.get("rate_limits") or {}).items()},
    )

    fresh_raw = raw.get("freshness", {})
    freshness = FreshnessSettings(
        max_age_hours=int(fresh_raw.get("max_age_hours", 24)),
        clock_skew_minutes=int(fresh_raw.get("clock_skew_minutes", 5)),
    )

    llm_raw = raw.get("llm", {})
    providers = tuple(
        LlmProviderConfig(
            name=str(p["name"]),
            api_key_env=str(p["api_key_env"]),
            model_env=str(p.get("model_env", "")),
            default_model=str(p.get("default_model", "")),
            endpoint=str(p["endpoint"]),
            max_input_chars=int(p.get("max_input_chars", 20000)),
        )
        for p in llm_raw.get("providers", [])
    )
    llm = LlmSettings(
        enabled=bool(llm_raw.get("enabled", True)),
        providers=providers,
        request_timeout_seconds=float(llm_raw.get("request_timeout_seconds", 90)),
        max_retries_per_provider=int(llm_raw.get("max_retries_per_provider", 2)),
        retry_base_seconds=float(llm_raw.get("retry_base_seconds", 2)),
        retry_max_seconds=float(llm_raw.get("retry_max_seconds", 30)),
        circuit_break_after_failures=int(llm_raw.get("circuit_break_after_failures", 3)),
        chunk_target_chars=int(llm_raw.get("chunk_target_chars", 12000)),
        chunk_overlap_chars=int(llm_raw.get("chunk_overlap_chars", 600)),
    )

    storage = raw.get("storage", {})
    entity_raw = raw.get("entity_resolution", {})
    entity = EntityResolutionSettings(
        exact_threshold=float(entity_raw.get("exact_threshold", 100)),
        alias_threshold=float(entity_raw.get("alias_threshold", 98)),
        domain_threshold=float(entity_raw.get("domain_threshold", 95)),
        auto_merge_threshold=float(entity_raw.get("auto_merge_threshold", 97)),
        review_threshold=float(entity_raw.get("review_threshold", 80)),
        min_auto_length_ratio=float(entity_raw.get("min_auto_length_ratio", 0.8)),
        min_auto_character_ratio=float(entity_raw.get("min_auto_character_ratio", 90)),
        name_max_tokens=int(entity_raw.get("name_max_tokens", 5)),
        name_max_chars=int(entity_raw.get("name_max_chars", 60)),
        seed_entity_file=str(entity_raw.get("seed_entity_file", "config/seed_entities.txt")),
    )
    sheets_raw = raw.get("sheets", {})
    sheets = SheetsSettings(
        spreadsheet_title=str(sheets_raw.get("spreadsheet_title", "FrontierAtlas Dataset")),
        tabs={str(k): str(v) for k, v in (sheets_raw.get("tabs") or {}).items()},
    )

    return AppSettings(
        http=http,
        freshness=freshness,
        llm=llm,
        entity_resolution=entity,
        sheets=sheets,
        database_path=_resolve(base, str(storage.get("database_path", "data/frontieratlas.db"))),
        raw_dir=_resolve(base, str(storage.get("raw_dir", "data/raw"))),
        processed_dir=_resolve(base, str(storage.get("processed_dir", "data/processed"))),
        export_dir=_resolve(base, str(storage.get("export_dir", "data/exports"))),
        sources=sources,
    )


def get_settings() -> AppSettings:
    return load_settings()


def project_root() -> Path:
    return PROJECT_ROOT
