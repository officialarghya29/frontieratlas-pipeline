#!/usr/bin/env python3
"""Enrich research papers that already contain explicit GitHub evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.common.http import AsyncHttpClient  # noqa: E402
from frontieratlas.enrichers.github import GitHubEnricher  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402


async def main_async(limit: int) -> int:
    settings = get_settings()
    db = Database(settings.database_path).connect()
    try:
        async with AsyncHttpClient(settings.http, raw_dir=settings.raw_dir, source_tag="github") as client:
            enricher = GitHubEnricher(settings, client, db)
            stats = await enricher.enrich(limit=limit)
    finally:
        db.close()

    payload = stats.as_dict() | {"github_token_present": bool(os.environ.get("GITHUB_TOKEN"))}
    print(json.dumps(payload, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich papers with GitHub star counts.")
    parser.add_argument("--limit", type=int, default=400, help="Maximum repositories to query")
    args = parser.parse_args()
    return asyncio.run(main_async(args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
