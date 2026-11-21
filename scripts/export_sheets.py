#!/usr/bin/env python3
"""Create/populate the six-tab Google Sheet, or validate the payload without credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.exporters.sheets import (  # noqa: E402
    MissingCredentials,
    build_payloads,
    export_to_sheets,
    scan_payloads,
)
from frontieratlas.storage.db import Database  # noqa: E402


def dry_run(settings, db) -> int:
    payloads = build_payloads(settings, db)
    findings = scan_payloads(payloads)
    result = {
        "status": "dry_run_ok" if not findings else "blocked_secret_scan",
        "tabs": {
            tab: {"rows": len(payload["rows"]), "columns": len(payload["headers"])}
            for tab, payload in payloads.items()
        },
        "total_data_rows": sum(len(payload["rows"]) for payload in payloads.values()),
        "secret_findings": findings,
        "credentials_present": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()),
        "next_step": (
            "Set GOOGLE_APPLICATION_CREDENTIALS and run without --dry-run, "
            "or upload data/exports/FrontierAtlas_submission.xlsx to Google Sheets and share it publicly."
        ),
    }
    print(json.dumps(result, indent=2))
    return 0 if not findings else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the dataset to Google Sheets.")
    parser.add_argument("--no-public", action="store_true", help="Do not grant public reader access")
    parser.add_argument("--dry-run", action="store_true", help="Validate payloads without Google credentials")
    args = parser.parse_args()

    settings = get_settings()
    db = Database(settings.database_path).connect()
    try:
        if args.dry_run:
            return dry_run(settings, db)
        result = export_to_sheets(settings, db, share_public=not args.no_public)
    except MissingCredentials as exc:
        print(json.dumps({
            "status": "blocked_missing_credentials",
            "message": str(exc),
            "remaining_step": (
                "Fastest path: upload data/exports/FrontierAtlas_submission.xlsx to Google Drive, "
                "open it with Google Sheets, and share it as 'Anyone with the link' (Viewer). "
                "API path: create a Google service account, enable the Google Sheets and Drive APIs, "
                "download the JSON key outside this repository, set GOOGLE_APPLICATION_CREDENTIALS, "
                "then rerun: python scripts/export_sheets.py"
            ),
            "csv_exports": str(settings.export_dir),
            "staging_workbook": str(settings.export_dir / "FrontierAtlas_submission.xlsx"),
        }, indent=2))
        return 3
    finally:
        db.close()

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
