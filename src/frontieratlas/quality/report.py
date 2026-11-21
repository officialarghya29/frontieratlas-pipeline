"""Data quality reporting across collection, enrichment, and resolution."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from ..common.config import AppSettings
from ..common.ids import iso_now
from ..common.text import domain_of
from ..exporters.datasets import TAB_TYPES, resolve_path
from ..storage.db import Database

FIELD_SPECS: dict[str, list[str]] = {
    "STARTUP": [
        "content.entityName",
        "content.data.employeeCount",
        "content.website",
        "content.description",
        "content.foundedYear",
        "content.industry",
        "content.headquarters",
        "provenance.recordUrl",
    ],
    "PRODUCT": [
        "content.entityName",
        "content.startupName",
        "content.pricingModel",
        "content.productUrl",
        "content.description",
        "content.category",
        "provenance.recordUrl",
    ],
    "RESEARCH_PAPER": [
        "content.title",
        "content.authors",
        "content.paper_url",
        "content.github_url",
        "content.github_stars",
        "content.github_checked_at",
        "content.published_date",
        "content.abstract",
    ],
    "JOB": [
        "content.company",
        "content.date",
        "content.is_remote",
        "content.role_family",
        "content.title",
        "content.job_url",
        "provenance.dateEvidence",
    ],
    "NEWS": [
        "content.title",
        "content.date",
        "content.publisher",
        "content.full_text",
        "content.summary",
        "content.article_url",
        "provenance.dateEvidence",
    ],
}


def _is_missing(record: dict, path: str) -> bool:
    value = resolve_path(record, path)
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _field_stats(records: list[dict], paths: list[str]) -> dict[str, dict[str, Any]]:
    total = len(records)
    stats: dict[str, dict[str, Any]] = {}
    for path in paths:
        missing = sum(1 for record in records if _is_missing(record, path))
        stats[path] = {
            "present": total - missing,
            "missing": missing,
            "missing_pct": round((missing / total) * 100, 2) if total else 0.0,
        }
    return stats


def _load_test_results(settings: AppSettings) -> dict | None:
    path = settings.processed_dir / "test_results.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _load_llm_report(settings: AppSettings) -> dict:
    path = settings.processed_dir / "llm_extraction.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "status": "pending",
        "reason": "No LLM provider credentials were configured for this run; raw content is preserved for re-extraction.",
        "successes": 0,
        "failures": 0,
        "provider_health": [],
    }


def build_quality_report(settings: AppSettings, db: Database) -> dict:
    latest_run = db.latest_run() or {}
    run_summary = latest_run.get("summary") or {}
    run_sources = run_summary.get("sources", [])

    records = {record_type: db.fetch_records(record_type) for record_type in TAB_TYPES if record_type != "ENTITY_MAPPING"}
    mappings = db.fetch_mappings()
    counts = db.count_by_type()

    missing_stats = {record_type: _field_stats(items, FIELD_SPECS[record_type]) for record_type, items in records.items()}

    papers = records.get("RESEARCH_PAPER", [])
    with_repo = [p for p in papers if p["content"].get("github_url")]
    with_stars = [p for p in papers if isinstance(p["content"].get("github_stars"), int)]
    star_values = [p["content"]["github_stars"] for p in with_stars]

    news = records.get("NEWS", [])
    jobs = records.get("JOB", [])
    rejection_counts: dict[str, int] = {}
    for source in run_sources:
        for reason, count in (source.get("rejections_by_reason") or {}).items():
            rejection_counts[reason] = rejection_counts.get(reason, 0) + int(count)

    decision_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    for mapping in mappings:
        decision_counts[mapping["decision"]] = decision_counts.get(mapping["decision"], 0) + 1
        method_counts[mapping["method"]] = method_counts.get(mapping["method"], 0) + 1

    def date_range(items: list[dict]) -> dict[str, Any]:
        dates = sorted(item["content"].get("date") for item in items if item["content"].get("date"))
        return {"min": dates[0] if dates else None, "max": dates[-1] if dates else None, "count": len(dates)}

    source_domains: dict[str, int] = {}
    for record in records.get("STARTUP", []):
        domain = domain_of(record["content"].get("website"))
        if domain:
            source_domains[domain] = source_domains.get(domain, 0) + 1
    duplicate_domains = {domain: count for domain, count in source_domains.items() if count > 1}

    report = {
        "generated_at": iso_now(),
        "run": {
            "run_id": latest_run.get("run_id"),
            "started_at": latest_run.get("started_at"),
            "finished_at": latest_run.get("finished_at"),
            "status": latest_run.get("status"),
            "duration_seconds": run_summary.get("duration_seconds"),
        },
        "counts": {
            "by_type": counts,
            "total_dataset_records": sum(value for key, value in counts.items()),
            "entity_mappings": len(mappings),
        },
        "targets": {
            "STARTUP": {"target": 1000, "actual": counts.get("STARTUP", 0), "met": counts.get("STARTUP", 0) >= 1000},
            "PRODUCT": {"target": 1000, "actual": counts.get("PRODUCT", 0), "met": counts.get("PRODUCT", 0) >= 1000},
            "RESEARCH_PAPER": {"target": 1000, "actual": counts.get("RESEARCH_PAPER", 0), "met": counts.get("RESEARCH_PAPER", 0) >= 1000},
        },
        "sources": run_sources,
        "source_runs": db.fetch_source_runs(),
        "rejections": {
            "by_reason": dict(sorted(rejection_counts.items(), key=lambda item: (-item[1], item[0]))),
            "cross_source_duplicates_removed": run_summary.get("cross_source_duplicates_removed", 0),
            "duplicate_startup_domains": duplicate_domains,
        },
        "missing_fields": missing_stats,
        "freshness": {
            "policy": {
                "max_age_hours": settings.freshness.max_age_hours,
                "clock_skew_minutes": settings.freshness.clock_skew_minutes,
            },
            "news": {
                "records": len(news),
                "verified": sum(1 for item in news if item.get("freshness_verified")),
                "date_range": date_range(news),
                "full_text": sum(1 for item in news if item.get("extraction_status") == "FULL_TEXT"),
                "summary_only": sum(1 for item in news if item.get("extraction_status") == "SUMMARY_ONLY"),
            },
            "jobs": {
                "records": len(jobs),
                "verified": sum(1 for item in jobs if item.get("freshness_verified")),
                "date_range": date_range(jobs),
                "remote_true": sum(1 for item in jobs if item["content"].get("is_remote") is True),
            },
            "rejections": {
                reason: count
                for reason, count in rejection_counts.items()
                if reason in {
                    "stale_publication_timestamp",
                    "future_publication_timestamp",
                    "missing_publication_date",
                    "invalid_publication_date",
                }
            },
        },
        "github_enrichment": {
            "papers": len(papers),
            "papers_with_explicit_repo": len(with_repo),
            "papers_with_star_count": len(with_stars),
            "median_stars": median(star_values) if star_values else None,
            "max_stars": max(star_values) if star_values else None,
            "checked_at_present": sum(1 for p in papers if p["content"].get("github_checked_at")),
        },
        "entity_resolution": {
            "decisions": decision_counts,
            "methods": method_counts,
            "manual_review_required": sum(1 for mapping in mappings if mapping["review_required"]),
            "auto_matched": decision_counts.get("AUTO_MATCHED", 0),
        },
        "llm_extraction": _load_llm_report(settings),
        "api_failures": [
            {"source": source.get("source"), "error": source.get("error")}
            for source in run_sources
            if source.get("status") != "ok"
        ],
        "tests": _load_test_results(settings),
        "database": db.stats(),
    }
    return report


def render_markdown(report: dict) -> str:
    counts = report["counts"]["by_type"]
    lines = [
        "# FrontierAtlas Data Quality Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Collection run: {report['run'].get('run_id')} ({report['run'].get('status')})",
        "",
        "## Dataset counts",
        "",
        "| Record type | Records |",
        "| --- | ---: |",
    ]
    for record_type, count in sorted(counts.items()):
        lines.append(f"| {record_type} | {count:,} |")
    lines.append(f"| Entity mappings | {report['counts']['entity_mappings']:,} |")
    lines += ["", "## Targets", "", "| Target | Required | Actual | Met |", "| --- | ---: | ---: | :---: |"]
    for record_type, target in report["targets"].items():
        lines.append(f"| {record_type} | {target['target']:,} | {target['actual']:,} | {'yes' if target['met'] else 'no'} |")

    lines += ["", "## Sources", "", "| Source | Type | Discovered | Accepted | Rejected | Status |", "| --- | --- | ---: | ---: | ---: | --- |"]
    for source in report["sources"]:
        lines.append(
            f"| {source.get('source')} | {source.get('record_type')} | {source.get('discovered', 0):,} | "
            f"{source.get('accepted', 0):,} | {source.get('rejected', 0):,} | {source.get('status')} |"
        )

    lines += ["", "## Rejections by reason", "", "| Reason | Count |", "| --- | ---: |"]
    for reason, count in report["rejections"]["by_reason"].items():
        lines.append(f"| {reason} | {count:,} |")

    lines += ["", "## Missing field statistics", ""]
    for record_type, fields in report["missing_fields"].items():
        lines += [f"### {record_type}", "", "| Field | Present | Missing | Missing % |", "| --- | ---: | ---: | ---: |"]
        for field, stats in fields.items():
            lines.append(f"| {field} | {stats['present']:,} | {stats['missing']:,} | {stats['missing_pct']}% |")
        lines.append("")

    freshness = report["freshness"]
    lines += [
        "## Freshness verification",
        "",
        f"Policy: published within {freshness['policy']['max_age_hours']}h, clock skew {freshness['policy']['clock_skew_minutes']}m.",
        "",
        f"- News: {freshness['news']['verified']}/{freshness['news']['records']} verified; "
        f"date range {freshness['news']['date_range']['min']} → {freshness['news']['date_range']['max']}; "
        f"{freshness['news']['full_text']} full text, {freshness['news']['summary_only']} summary only.",
        f"- Jobs: {freshness['jobs']['verified']}/{freshness['jobs']['records']} verified; "
        f"date range {freshness['jobs']['date_range']['min']} → {freshness['jobs']['date_range']['max']}; "
        f"{freshness['jobs']['remote_true']} remote.",
        f"- Freshness rejections: {json.dumps(freshness['rejections'])}",
        "",
        "## GitHub enrichment",
        "",
        f"- Papers: {report['github_enrichment']['papers']:,}",
        f"- Papers with explicit repository evidence: {report['github_enrichment']['papers_with_explicit_repo']:,}",
        f"- Papers with verified star counts: {report['github_enrichment']['papers_with_star_count']:,}",
        f"- Median stars: {report['github_enrichment']['median_stars']}",
        f"- Maximum stars: {report['github_enrichment']['max_stars']}",
        "",
        "## Entity resolution",
        "",
        f"- Decisions: {json.dumps(report['entity_resolution']['decisions'])}",
        f"- Methods: {json.dumps(report['entity_resolution']['methods'])}",
        f"- Manual review required: {report['entity_resolution']['manual_review_required']:,}",
        "",
        "## LLM extraction",
        "",
        f"- Status: {report['llm_extraction'].get('status')}",
        f"- Reason: {report['llm_extraction'].get('reason')}",
        "",
        "## API failures",
        "",
    ]
    if report["api_failures"]:
        for failure in report["api_failures"]:
            lines.append(f"- {failure['source']}: {failure['error']}")
    else:
        lines.append("- None")
    lines += ["", "## Tests", ""]
    tests = report.get("tests")
    if tests:
        lines.append(f"- {tests.get('passed', 0)} passed, {tests.get('failed', 0)} failed, {tests.get('errors', 0)} errors")
    else:
        lines.append("- No test result file found at the time this report was generated.")
    lines.append("")
    return "\n".join(lines)


def write_quality_report(settings: AppSettings, db: Database) -> dict:
    report = build_quality_report(settings, db)
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    json_path = settings.export_dir / "data_quality_report.json"
    md_path = settings.export_dir / "data_quality_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report
