#!/usr/bin/env python3
"""Measured local write throughput for the current SQLite schema.

This is a micro-benchmark of normalization + idempotent upserts on this machine,
not a claim that 500,000 real records have been collected or processed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.ids import iso_now  # noqa: E402
from frontieratlas.common.text import stable_id  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402


def main() -> int:
    count = 5000
    path = ROOT / "data" / "benchmark.db"
    if path.exists():
        path.unlink()
    db = Database(path).connect()
    records = []
    now = iso_now()
    for index in range(count):
        records.append(
            {
                "schemaVersion": "1.0",
                "recordType": "STARTUP",
                "record_id": stable_id("BENCH", index),
                "source": {"name": "benchmark", "url": "https://example.invalid/benchmark"},
                "content": {
                    "entityName": f"Benchmark Entity {index}",
                    "data": {"employeeCount": index % 500},
                    "website": f"https://benchmark-{index}.example.invalid",
                    "description": "Synthetic benchmark row; never exported or counted as collected data.",
                    "foundedYear": 2020,
                    "industry": "Benchmark",
                    "headquarters": None,
                },
                "provenance": {"recordUrl": f"https://example.invalid/benchmark/{index}"},
                "collectedAt": now,
            }
        )

    started = time.perf_counter()
    counts = db.upsert_records(records)
    elapsed = time.perf_counter() - started
    size = path.stat().st_size
    db.close()
    path.unlink(missing_ok=True)

    result = {
        "benchmark_records": count,
        "inserted": counts["inserted"],
        "elapsed_seconds": round(elapsed, 3),
        "records_per_second": round(count / elapsed, 1),
        "database_bytes": size,
        "note": "Synthetic benchmark rows are written to a temporary database and deleted; they are not part of the dataset.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
