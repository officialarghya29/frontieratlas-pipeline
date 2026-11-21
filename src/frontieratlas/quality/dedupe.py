"""Cross-source deduplication keys used before persistence."""

from __future__ import annotations

from typing import Iterable

from ..common.text import canonical_url, domain_of, normalize_name
from ..collectors.base import CollectorOutput


def dedupe_key(record: dict) -> str:
    record_type = record.get("recordType")
    content = record.get("content", {}) or {}
    if record_type == "STARTUP":
        return f"STARTUP::{domain_of(content.get('website')) or normalize_name(content.get('entityName'))}"
    if record_type == "PRODUCT":
        return f"PRODUCT::{canonical_url(content.get('productUrl')) or normalize_name(content.get('entityName'))}"
    if record_type == "RESEARCH_PAPER":
        return f"PAPER::{record.get('record_id')}"
    if record_type == "JOB":
        url = canonical_url(content.get("job_url"))
        pair = f"{normalize_name(content.get('company'))}::{normalize_name(content.get('title'))}"
        return f"JOB::{url or pair}"
    if record_type == "NEWS":
        return f"NEWS::{canonical_url(content.get('article_url')) or normalize_name(content.get('title'))}"
    return f"{record_type}::{record.get('record_id')}"


def dedupe_outputs(outputs: Iterable[CollectorOutput]) -> int:
    """Remove records already seen in an earlier source. Returns removed count."""

    seen: set[str] = set()
    removed = 0
    for output in outputs:
        kept: list[dict] = []
        for record in output.records:
            key = dedupe_key(record)
            if key in seen:
                output.add_rejection(
                    "duplicate_across_sources",
                    str(record.get("content", {}).get("entityName") or record.get("record_id")),
                    None,
                )
                removed += 1
                continue
            seen.add(key)
            kept.append(record)
        output.records = kept
    return removed
