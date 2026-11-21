"""CSV and JSONL exports for all six deliverables.

Column order is explicit and stable so repeated exports are byte-comparable
apart from the generated timestamp in the manifest.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..common.config import AppSettings, display_path
from ..common.ids import iso_now
from ..common.text import remove_control_chars
from ..storage.db import Database

TAB_TYPES = ["STARTUP", "PRODUCT", "RESEARCH_PAPER", "JOB", "NEWS", "ENTITY_MAPPING"]

FILE_STEMS = {
    "STARTUP": "startups",
    "PRODUCT": "products",
    "RESEARCH_PAPER": "research_papers",
    "JOB": "jobs",
    "NEWS": "news",
    "ENTITY_MAPPING": "entity_mapping_log",
}

MAPPING_COLUMNS = [
    "raw_name",
    "canonical_name",
    "entity_type",
    "source_url",
    "method",
    "similarity_score",
    "decision",
    "review_required",
    "mapped_at",
    "notes",
]

COLUMNS: dict[str, list[tuple[str, str]]] = {
    "STARTUP": [
        ("schemaVersion", "schemaVersion"),
        ("recordType", "recordType"),
        ("record_id", "record_id"),
        ("source_name", "source.name"),
        ("source_url", "source.url"),
        ("entityName", "content.entityName"),
        ("employeeCount", "content.data.employeeCount"),
        ("website", "content.website"),
        ("description", "content.description"),
        ("foundedYear", "content.foundedYear"),
        ("industry", "content.industry"),
        ("headquarters", "content.headquarters"),
        ("recordUrl", "provenance.recordUrl"),
        ("collectedAt", "collectedAt"),
    ],
    "PRODUCT": [
        ("schemaVersion", "schemaVersion"),
        ("recordType", "recordType"),
        ("record_id", "record_id"),
        ("source_name", "source.name"),
        ("source_url", "source.url"),
        ("entityName", "content.entityName"),
        ("startupName", "content.startupName"),
        ("pricingModel", "content.pricingModel"),
        ("productUrl", "content.productUrl"),
        ("description", "content.description"),
        ("category", "content.category"),
        ("recordUrl", "provenance.recordUrl"),
        ("collectedAt", "collectedAt"),
    ],
    "RESEARCH_PAPER": [
        ("schemaVersion", "schemaVersion"),
        ("recordType", "recordType"),
        ("record_id", "record_id"),
        ("source_name", "source.name"),
        ("source_url", "source.url"),
        ("title", "content.title"),
        ("authors", "content.authors"),
        ("paper_url", "content.paper_url"),
        ("github_url", "content.github_url"),
        ("github_stars", "content.github_stars"),
        ("github_checked_at", "content.github_checked_at"),
        ("published_date", "content.published_date"),
        ("abstract", "content.abstract"),
        ("recordUrl", "provenance.recordUrl"),
        ("githubEvidenceUrl", "provenance.githubEvidenceUrl"),
        ("collectedAt", "collectedAt"),
    ],
    "JOB": [
        ("schemaVersion", "schemaVersion"),
        ("recordType", "recordType"),
        ("record_id", "record_id"),
        ("source_name", "source.name"),
        ("source_url", "source.url"),
        ("company", "content.company"),
        ("date", "content.date"),
        ("is_remote", "content.is_remote"),
        ("role_family", "content.role_family"),
        ("title", "content.title"),
        ("job_url", "content.job_url"),
        ("recordUrl", "provenance.recordUrl"),
        ("dateEvidence", "provenance.dateEvidence"),
        ("freshness_verified", "freshness_verified"),
        ("collectedAt", "collectedAt"),
    ],
    "NEWS": [
        ("schemaVersion", "schemaVersion"),
        ("recordType", "recordType"),
        ("record_id", "record_id"),
        ("source_name", "source.name"),
        ("source_url", "source.url"),
        ("title", "content.title"),
        ("date", "content.date"),
        ("publisher", "content.publisher"),
        ("full_text", "content.full_text"),
        ("summary", "content.summary"),
        ("article_url", "content.article_url"),
        ("recordUrl", "provenance.recordUrl"),
        ("dateEvidence", "provenance.dateEvidence"),
        ("freshness_verified", "freshness_verified"),
        ("extraction_status", "extraction_status"),
        ("collectedAt", "collectedAt"),
    ],
}


def resolve_path(payload: Any, dotted: str) -> Any:
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(remove_control_chars(str(item)) for item in value)
    if isinstance(value, dict):
        return remove_control_chars(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return remove_control_chars(str(value))


def headers_for(record_type: str) -> list[str]:
    if record_type == "ENTITY_MAPPING":
        return list(MAPPING_COLUMNS)
    return [header for header, _ in COLUMNS[record_type]]


def rows_for(record_type: str, records: Iterable[dict]) -> list[list[str]]:
    if record_type == "ENTITY_MAPPING":
        return [
            [format_cell(record.get(column)) for column in MAPPING_COLUMNS]
            for record in records
        ]
    return [
        [format_cell(resolve_path(record, path)) for _, path in COLUMNS[record_type]]
        for record in records
    ]


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def export_datasets(settings: AppSettings, db: Database) -> dict:
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "generated_at": iso_now(),
        "database": display_path(db.path),
        "tabs": {},
        "files": {},
    }

    for record_type in TAB_TYPES:
        if record_type == "ENTITY_MAPPING":
            records: list[dict] = db.fetch_mappings()
        else:
            records = db.fetch_records(record_type)
        headers = headers_for(record_type)
        rows = rows_for(record_type, records)
        stem = FILE_STEMS[record_type]
        csv_path = settings.export_dir / f"{stem}.csv"
        jsonl_path = settings.export_dir / f"{stem}.jsonl"
        _write_csv(csv_path, headers, rows)
        _write_jsonl(jsonl_path, records)
        manifest["tabs"][record_type] = {
            "tab_name": settings.tab_name(record_type) if record_type != "ENTITY_MAPPING" else settings.sheets.tabs.get("ENTITY_MAPPING", "Entity Mapping Log"),
            "headers": headers,
            "rows": len(rows),
            "csv": csv_path.name,
            "jsonl": jsonl_path.name,
        }
        manifest["files"][csv_path.name] = {"bytes": csv_path.stat().st_size, "sha256": _sha256(csv_path)}
        manifest["files"][jsonl_path.name] = {"bytes": jsonl_path.stat().st_size, "sha256": _sha256(jsonl_path)}

    manifest["total_records"] = sum(
        item["rows"] for key, item in manifest["tabs"].items() if key != "ENTITY_MAPPING"
    )
    manifest["entity_mappings"] = manifest["tabs"]["ENTITY_MAPPING"]["rows"]
    manifest_path = settings.export_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
