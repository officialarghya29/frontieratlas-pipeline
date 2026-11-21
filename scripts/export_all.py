#!/usr/bin/env python3
"""Write the six CSV/JSONL deliverables and a manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.exporters.datasets import export_datasets  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402


def main() -> int:
    settings = get_settings()
    db = Database(settings.database_path).connect()
    try:
        manifest = export_datasets(settings, db)
    finally:
        db.close()
    print(json.dumps({
        "export_dir": str(settings.export_dir),
        "tabs": {key: value["rows"] for key, value in manifest["tabs"].items()},
        "total_records": manifest["total_records"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
