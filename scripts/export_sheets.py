#!/usr/bin/env python3
"""Create/populate the six-tab Google Sheet and make it publicly viewable."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.exporters.sheets import MissingCredentials, export_to_sheets  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the dataset to Google Sheets.")
    parser.add_argument("--no-public", action="store_true", help="Do not grant public reader access")
    args = parser.parse_args()

    settings = get_settings()
    db = Database(settings.database_path).connect()
    try:
        result = export_to_sheets(settings, db, share_public=not args.no_public)
    except MissingCredentials as exc:
        print(json.dumps({
            "status": "blocked_missing_credentials",
            "message": str(exc),
            "remaining_step": (
                "Create a Google service account, enable the Google Sheets and Drive APIs, "
                "download the JSON key outside this repository, set GOOGLE_APPLICATION_CREDENTIALS "
                "to its path, then rerun: python scripts/export_sheets.py"
            ),
            "csv_exports": str(settings.export_dir),
        }, indent=2))
        return 3
    finally:
        db.close()

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
