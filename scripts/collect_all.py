#!/usr/bin/env python3
"""Run every enabled collector, deduplicate across sources, then persist.

Order of operations matters for data integrity:
1. Every source is collected concurrently and in isolation.
2. Duplicates are removed across sources *before* any database write.
3. Only surviving records are upserted (idempotent, keyed by record_id).
4. Per-source run metadata and a full JSON report are written.

A failing source is recorded as failed; the run continues.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.collectors.base import CollectorContext, CollectorOutput  # noqa: E402
from frontieratlas.collectors.registry import build_collectors  # noqa: E402
from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.common.http import AsyncHttpClient  # noqa: E402
from frontieratlas.common.ids import iso_now  # noqa: E402
from frontieratlas.common.logging import get_logger  # noqa: E402
from frontieratlas.quality.dedupe import dedupe_outputs  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402

log = get_logger("collect")


def _rejection_counts(output: CollectorOutput) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rejection in output.rejections:
        counts[rejection.reason] = counts.get(rejection.reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


async def collect_one(collector: Any, ctx: CollectorContext) -> dict:
    started = time.perf_counter()
    base = {
        "source": collector.name,
        "record_type": collector.record_type,
        "source_url": getattr(collector, "source_url", None),
    }
    try:
        output = await collector.collect(ctx)
    except Exception as exc:  # noqa: BLE001 - failing sources are isolated by design
        duration = round(time.perf_counter() - started, 2)
        log.exception("collector failed", extra={"source": collector.name})
        ctx.db.record_source_run(
            collector.name,
            source_url=base["source_url"],
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:500],
            ran_at=iso_now(ctx.now),
        )
        return {
            **base,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "discovered": 0,
            "accepted": 0,
            "rejected": 0,
            "rejections_by_reason": {},
            "notes": [],
            "duration_seconds": duration,
        }

    return {
        **base,
        "status": "ok",
        "discovered": output.discovered,
        "accepted": 0,  # filled after cross-source dedupe
        "rejected": 0,
        "rejections_by_reason": {},
        "rejection_samples": [
            {"reason": r.reason, "detail": r.detail, "source_url": r.source_url}
            for r in output.rejections[:15]
        ],
        "notes": output.notes,
        "source_meta": output.source_meta,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "output": output,
    }


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.raw_dir.mkdir(parents=True, exist_ok=True)

    db = Database(settings.database_path).connect()
    now = datetime.now(timezone.utc)
    run_id = args.run_id or f"run-{now.strftime('%Y%m%dT%H%M%SZ')}"
    db.start_run(run_id, iso_now(now))

    collectors = build_collectors(settings)
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        collectors = [c for c in collectors if c.name in wanted]
    if not collectors:
        print("No collectors selected.", file=sys.stderr)
        return 2

    log.info("starting collection run %s with %d collectors", run_id, len(collectors))

    async with AsyncHttpClient(settings.http, raw_dir=settings.raw_dir, source_tag=run_id) as client:
        ctx = CollectorContext(settings=settings, client=client, db=db, now=now)
        results = await asyncio.gather(*(collect_one(collector, ctx) for collector in collectors))
        raw_files = list(client.raw_files)

    outputs: list[CollectorOutput] = []
    for result in results:
        output = result.pop("output", None)
        if output is not None:
            outputs.append(output)

    duplicates = dedupe_outputs(outputs)
    observed_at = iso_now(now)

    for output in outputs:
        counts = db.upsert_records(output.records, observed_at=observed_at)
        db.record_source_run(
            output.source_name,
            source_url=output.source_meta.get("source_url"),
            status="ok",
            discovered=output.discovered,
            accepted=output.accepted,
            rejected=output.rejected,
            ran_at=observed_at,
        )
        matching = next((r for r in results if r["source"] == output.source_name), None)
        if matching is not None:
            matching["accepted"] = output.accepted
            matching["rejected"] = output.rejected
            matching["rejections_by_reason"] = _rejection_counts(output)
            matching["upsert"] = counts

    finished = datetime.now(timezone.utc)
    counts_by_type = db.count_by_type()
    report = {
        "run_id": run_id,
        "started_at": iso_now(now),
        "finished_at": iso_now(finished),
        "duration_seconds": round((finished - now).total_seconds(), 2),
        "counts_by_type": counts_by_type,
        "total_records": db.total_records(),
        "cross_source_duplicates_removed": duplicates,
        "sources": results,
        "raw_files_saved": len(raw_files),
        "source_failures": [r["source"] for r in results if r["status"] == "failed"],
        "sqlite_stats": db.stats(),
    }

    report_path = settings.processed_dir / f"run_{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    db.finish_run(run_id, finished_at=iso_now(finished), status="completed", summary=report)
    db.close()

    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2, ensure_ascii=False))
    for source in results:
        print(
            f"{source['source']:22s} {source['record_type']:15s} status={source['status']:7s} "
            f"discovered={source['discovered']:6d} accepted={source['accepted']:5d} "
            f"rejected={source['rejected']:6d} {source.get('error') or ''}",
            file=sys.stderr,
        )
    print(f"\nRun report written to {report_path}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FrontierAtlas collectors.")
    parser.add_argument("--only", default="", help="Comma-separated collector names to run")
    parser.add_argument("--run-id", default="", help="Explicit run id")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
