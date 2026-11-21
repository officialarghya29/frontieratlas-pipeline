from __future__ import annotations

import json
from dataclasses import replace

from frontieratlas.common.config import get_settings
from frontieratlas.exporters.datasets import export_datasets
from frontieratlas.exporters.sheets import build_payloads
from frontieratlas.quality.safety import scan_rows
from frontieratlas.storage.db import Database


def _startup() -> dict:
    return {
        "schemaVersion": "1.0",
        "recordType": "STARTUP",
        "record_id": "s1",
        "source": {"name": "YC", "url": "https://example.com/yc.json"},
        "content": {
            "entityName": "Acme AI",
            "data": {"employeeCount": 42},
            "website": "https://acme.example",
            "description": "AI company",
            "foundedYear": 2020,
            "industry": "AI",
            "headquarters": "SF",
        },
        "provenance": {"recordUrl": "https://example.com/acme"},
        "collectedAt": "2026-11-21T06:00:00Z",
    }


def test_six_tabs_and_header_mapping(tmp_path):
    db = Database(tmp_path / "test.db").connect()
    db.upsert_records([_startup()])
    payloads = build_payloads(get_settings(), db)
    assert list(payloads) == ["Startups", "Products", "Research Papers", "Jobs", "News", "Entity Mapping Log"]
    startups = payloads["Startups"]
    assert "employeeCount" in startups["headers"]
    row = startups["rows"][0]
    assert row[startups["headers"].index("entityName")] == "Acme AI"
    assert row[startups["headers"].index("employeeCount")] == "42"
    db.close()


def test_csv_and_jsonl_exports(tmp_path):
    db = Database(tmp_path / "test.db").connect()
    db.upsert_records([_startup()])
    settings = replace(get_settings(), export_dir=tmp_path / "exports")
    manifest = export_datasets(settings, db)
    assert manifest["tabs"]["STARTUP"]["rows"] == 1
    assert manifest["database"] == "test.db"
    csv_text = (tmp_path / "exports" / "startups.csv").read_text(encoding="utf-8")
    assert csv_text.splitlines()[0].startswith("schemaVersion,recordType,record_id")
    jsonl_lines = (tmp_path / "exports" / "startups.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == 1
    assert json.loads(jsonl_lines[0])["content"]["entityName"] == "Acme AI"
    assert (tmp_path / "exports" / "manifest.json").exists()
    db.close()


def test_secret_scanner_blocks_credential_shapes():
    token = "ghp_" + "a" * 36
    findings = scan_rows([["safe", token]])
    assert "github_classic_token" in findings
    assert scan_rows([["ordinary dataset text"]]) == []
