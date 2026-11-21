#!/usr/bin/env python3
"""Preflight verification of every local submission requirement.

Fails on missing files, count shortfalls, schema errors, PDF over three pages,
failing tests, wrong commit identity, AI attribution, or credential-shaped
content. Google Sheet and LLM credentials are reported as external actions,
never silently treated as complete.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openpyxl import load_workbook  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.exporters.datasets import TAB_TYPES  # noqa: E402
from frontieratlas.exporters.sheets import build_payloads, scan_payloads  # noqa: E402
from frontieratlas.quality.safety import scan_text  # noqa: E402
from frontieratlas.schemas import EntityMapping, validate_record  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402

TABS = ["Startups", "Products", "Research Papers", "Jobs", "News", "Entity Mapping Log"]
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".txt", ".csv", ".json", ".jsonl", ".ini", ".toml", ".example", ".gitignore"}
MAX_SCAN_BYTES = 6 * 1024 * 1024
EXPECTED_AUTHOR_EMAIL = "officialarghya29@gmail.com"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    ).stdout.strip()


def main() -> int:
    settings = get_settings()
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    required = [
        "README.md",
        "architecture.pdf",
        "SUBMISSION.md",
        "requirements.txt",
        "pyproject.toml",
        ".env.example",
        "IMPLEMENTATION_PLAN.md",
        "PROGRESS.md",
        "config/settings.yaml",
        "config/sources.yaml",
        "src/frontieratlas/schemas.py",
        "data/exports/startups.csv",
        "data/exports/products.csv",
        "data/exports/research_papers.csv",
        "data/exports/jobs.csv",
        "data/exports/news.csv",
        "data/exports/entity_mapping_log.csv",
        "data/exports/manifest.json",
        "data/exports/data_quality_report.md",
        "data/exports/FrontierAtlas_submission.xlsx",
    ]
    missing = [path for path in required if not (ROOT / path).exists()]
    check("required files", not missing, "all present" if not missing else f"missing: {missing}")

    db = Database(settings.database_path).connect()
    counts = db.count_by_type()
    mappings = db.count_mappings()
    targets = {"STARTUP": 1000, "PRODUCT": 1000, "RESEARCH_PAPER": 1000}
    target_ok = all(counts.get(record_type, 0) >= minimum for record_type, minimum in targets.items())
    check("record targets", target_ok, f"counts={counts}")

    schema_issues: list[str] = []
    for record_type in TAB_TYPES:
        if record_type == "ENTITY_MAPPING":
            continue
        for record in db.fetch_records(record_type):
            try:
                validate_record(record)
            except Exception as exc:  # noqa: BLE001
                schema_issues.append(f"{record_type}:{record.get('record_id')}: {exc}")
    for mapping in db.fetch_mappings():
        try:
            EntityMapping.model_validate(mapping)
        except Exception as exc:  # noqa: BLE001
            schema_issues.append(f"ENTITY_MAPPING:{mapping.get('raw_name')}: {exc}")
    check("schema validation", not schema_issues, f"{len(schema_issues)} issue(s)")

    fresh_ok = all(
        record.get("freshness_verified") is True
        for record_type in ("JOB", "NEWS")
        for record in db.fetch_records(record_type)
    )
    check("24h freshness flags", fresh_ok, "all job/news records verified")

    payloads = build_payloads(settings, db)
    tab_names = list(payloads)
    check("six sheet tabs", tab_names == TABS, f"tabs={tab_names}")
    findings = scan_payloads(payloads)
    check("export secret scan", not findings, f"findings={findings}")

    manifest_path = ROOT / "data" / "exports" / "manifest.json"
    manifest_ok = False
    manifest_detail = "missing"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_rows = {
                "STARTUP": len(payloads["Startups"]["rows"]),
                "PRODUCT": len(payloads["Products"]["rows"]),
                "RESEARCH_PAPER": len(payloads["Research Papers"]["rows"]),
                "JOB": len(payloads["Jobs"]["rows"]),
                "NEWS": len(payloads["News"]["rows"]),
                "ENTITY_MAPPING": len(payloads["Entity Mapping Log"]["rows"]),
            }
            problems: list[str] = []
            manifest_tabs = manifest.get("tabs") or {}
            for record_type, count in expected_rows.items():
                actual = (manifest_tabs.get(record_type) or {}).get("rows", -1)
                if actual != count:
                    problems.append(f"{record_type} rows {actual}/{count}")
            expected_total = sum(count for key, count in expected_rows.items() if key != "ENTITY_MAPPING")
            if manifest.get("total_records") != expected_total:
                problems.append(f"total {manifest.get('total_records')}/{expected_total}")
            if manifest.get("entity_mappings") != expected_rows["ENTITY_MAPPING"]:
                problems.append("entity mapping total")
            database = str(manifest.get("database") or "")
            if not database or Path(database).is_absolute():
                problems.append(f"non-portable database path: {database!r}")
            files = manifest.get("files") or {}
            for filename, meta in files.items():
                path = settings.export_dir / filename
                if not path.is_file():
                    problems.append(f"missing {filename}")
                elif hashlib.sha256(path.read_bytes()).hexdigest() != meta.get("sha256"):
                    problems.append(f"hash {filename}")
            manifest_ok = not problems
            manifest_detail = (
                f"{len(files)} file hashes verified; database={database}"
                if manifest_ok
                else "; ".join(problems[:4])
            )
        except Exception as exc:  # noqa: BLE001 - malformed manifest is a failed check
            manifest_detail = f"invalid manifest: {type(exc).__name__}: {exc}"
    check("export manifest", manifest_ok, manifest_detail)

    workbook_path = ROOT / "data" / "exports" / "FrontierAtlas_submission.xlsx"
    workbook_ok = False
    workbook_detail = "missing"
    if workbook_path.exists():
        workbook = load_workbook(workbook_path, read_only=True)
        try:
            problems = []
            if workbook.sheetnames != TABS:
                problems.append(f"tabs={workbook.sheetnames}")
            for tab in TABS:
                if tab not in workbook.sheetnames:
                    continue
                sheet = workbook[tab]
                expected = payloads.get(tab, {"headers": [], "rows": []})
                header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
                if list(header_row) != expected["headers"]:
                    problems.append(f"{tab}: headers")
                if sheet.max_row - 1 != len(expected["rows"]):
                    problems.append(f"{tab}: rows {sheet.max_row - 1}/{len(expected['rows'])}")
                if sheet.max_column != len(expected["headers"]):
                    problems.append(f"{tab}: cols {sheet.max_column}/{len(expected['headers'])}")
            workbook_ok = not problems
            workbook_detail = (
                "six tabs, headers and row counts match" if workbook_ok else "; ".join(problems[:4])
            )
        finally:
            workbook.close()
    check("workbook contents", workbook_ok, workbook_detail)

    pdf_pages = 0
    pdf_path = ROOT / "architecture.pdf"
    if pdf_path.exists():
        pdf_pages = len(PdfReader(pdf_path).pages)
    check("architecture PDF", 0 < pdf_pages <= 3, f"{pdf_pages} page(s)")

    test_results_path = ROOT / "data" / "processed" / "test_results.json"
    test_results = json.loads(test_results_path.read_text()) if test_results_path.exists() else {}
    tests_ok = test_results.get("failed", 1) == 0 and test_results.get("errors", 1) == 0 and test_results.get("passed", 0) > 0
    check("automated tests", tests_ok, f"{test_results}")

    identities: list[list[str]] = []
    for line in git("log", "--format=%an%x1f%ae%x1f%cn%x1f%ce").splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            identities.append(parts)
    identity_ok = bool(identities) and all(
        author_name == "Arghya Bose"
        and author_email.lower() == EXPECTED_AUTHOR_EMAIL
        and committer_name == "Arghya Bose"
        and committer_email.lower() == EXPECTED_AUTHOR_EMAIL
        for author_name, author_email, committer_name, committer_email in identities
    )
    check(
        "commit identity",
        identity_ok,
        f"all commits under Arghya Bose <{EXPECTED_AUTHOR_EMAIL}>",
    )
    commit_bodies = git("log", "--format=%B").lower()
    attribution = any(
        marker in commit_bodies for marker in ("co-authored-by", "codebuff", "generated with", "🤖")
    )
    check("no AI attribution", not attribution, "all commit messages clean")

    secret_hits: list[str] = []
    tracked = git("ls-files", "-z").split("\0")
    for relative in tracked:
        if not relative:
            continue
        path = ROOT / relative
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.exists():
            continue
        if path.stat().st_size > MAX_SCAN_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for finding in scan_text(text):
            secret_hits.append(f"{relative}:{finding}")
    check("repository secret scan", not secret_hits, f"{len(secret_hits)} finding(s)")

    sheet_ready = bool(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        and Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).exists()
    )
    llm_ready = any(os.environ.get(key, "").strip() for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"))
    workbook_ready = workbook_path.exists()

    local_ok = all(item["ok"] for item in checks)
    external_actions: list[str] = []
    if not sheet_ready:
        external_actions.append(
            "Google Sheet: upload data/exports/FrontierAtlas_submission.xlsx to Google Drive, "
            "open with Google Sheets, share 'Anyone with the link' (Viewer), paste the URL into the form."
        )
    if not llm_ready:
        external_actions.append(
            "LLM extraction: set GEMINI_API_KEY/GROQ_API_KEY/DEEPSEEK_API_KEY and run "
            "python scripts/extract_llm.py, then re-export and rebuild the workbook."
        )

    summary = {
        "ready_to_submit_local": local_ok and workbook_ready,
        "repository": git("remote", "get-url", "origin"),
        "counts": counts,
        "entity_mappings": mappings,
        "pdf_pages": pdf_pages,
        "tests": test_results,
        "sheet_api_ready": sheet_ready,
        "llm_ready": llm_ready,
        "workbook": str(workbook_path.relative_to(ROOT)) if workbook_ready else None,
        "external_actions_required": external_actions,
        "checks": checks,
    }
    summary_path = settings.export_dir / "submission_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    for item in checks:
        print(f"{'PASS' if item['ok'] else 'FAIL'}  {item['check']}: {item['detail']}")
    print(f"\nRepository: {summary['repository']}")
    print(f"Counts: {counts} | mappings: {mappings} | PDF: {pdf_pages} pages | tests: {test_results.get('passed', 0)} passing")
    if external_actions:
        print("\nExternal actions remaining (not failures of the repository):")
        for action in external_actions:
            print(f"  - {action}")
    print(f"\nSummary written to {summary_path}")
    print(f"LOCAL SUBMISSION READY: {'YES' if summary['ready_to_submit_local'] else 'NO'}")
    db.close()
    return 0 if summary["ready_to_submit_local"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
