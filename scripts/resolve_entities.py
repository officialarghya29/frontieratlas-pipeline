#!/usr/bin/env python3
"""Resolve product entities against canonical startup entities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.resolvers.entities import EntityResolver  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402


def main() -> int:
    settings = get_settings()
    db = Database(settings.database_path).connect()
    try:
        resolver = EntityResolver(settings.entity_resolution, db)
        stats = resolver.resolve_products()
        print(json.dumps(stats.as_dict(), indent=2))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
