#!/usr/bin/env python3
"""Revalidate every stored record, check targets, and write the quality report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.exporters.datasets import TAB_TYPES  # noqa: E402
from frontieratlas.quality.report import write_quality_report  # noqa: E402
from frontieratlas.schemas import EntityMapping, validate_record  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402

MINIMUMS = {"STARTUP": 1000, "PRODUCT": 1000, "RESEARCH_PAPER": 1000}


def main() -> int:
    settings = get_settings()
    db = Database(settings.database_path).connect()
    issues: list[str] = []
    try:
        counts = db.count_by_type()
        for record_type in TAB_TYPES:
            if record_type == "ENTITY_MAPPING":
                continue
            for record in db.fetch_records(record_type):
                try:
                    validate_record(record)
                except Exception as exc:  # noqa: BLE001 - collect all failures
                    issues.append(f"{record_type} {record.get('record_id')}: {exc}")
                source_url = record.get("source", {}).get("url")
                provenance_url = record.get("provenance", {}).get("recordUrl")
                if not source_url or not provenance_url:
                    issues.append(f"{record_type} {record.get('record_id')}: missing source/provenance URL")
                if record_type in {"JOB", "NEWS"} and record.get("freshness_verified") is not True:
                    issues.append(f"{record_type} {record.get('record_id')}: freshness not verified")
        for mapping in db.fetch_mappings():
            try:
                EntityMapping.model_validate(mapping)
            except Exception as exc:  # noqa: BLE001
                issues.append(f"ENTITY_MAPPING {mapping.get('raw_name')}: {exc}")

        targets = {
            record_type: {"required": minimum, "actual": counts.get(record_type, 0), "met": counts.get(record_type, 0) >= minimum}
            for record_type, minimum in MINIMUMS.items()
        }
        report = write_quality_report(settings, db)
    finally:
        db.close()

    summary = {
        "records_by_type": counts,
        "targets": targets,
        "schema_issues": len(issues),
        "schema_issue_samples": issues[:20],
        "quality_report": report["paths"],
    }
    print(json.dumps(summary, indent=2))
    if issues:
        return 1
    if not all(target["met"] for target in targets.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
