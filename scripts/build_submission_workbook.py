#!/usr/bin/env python3
"""Build a six-tab XLSX staging workbook for one-click Google Sheets publishing.

The workbook is not a substitute for the Google Sheet deliverable: it is a
credential-free handoff. Upload it to Google Drive, open with Google Sheets,
and share it publicly. The API exporter remains available when credentials
exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.common.text import remove_control_chars  # noqa: E402
from frontieratlas.exporters.sheets import build_payloads, scan_payloads  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
WIDE_COLUMNS = {"description", "full_text", "summary", "abstract", "notes"}
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe(value: object) -> object:
    """Prevent spreadsheet formula injection from source-provided text."""

    if isinstance(value, str):
        value = remove_control_chars(value)
        if value.startswith(FORMULA_PREFIXES):
            return "'" + value
    return value


def build(path: Path) -> dict:
    settings = get_settings()
    db = Database(settings.database_path).connect()
    try:
        payloads = build_payloads(settings, db)
        findings = scan_payloads(payloads)
        if findings:
            raise SystemExit(f"Refusing to build workbook; credential-shaped content found: {findings}")

        workbook = Workbook()
        workbook.remove(workbook.active)
        for tab, payload in payloads.items():
            sheet = workbook.create_sheet(title=tab)
            sheet.append(payload["headers"])
            for row in payload["rows"]:
                sheet.append([_safe(value) for value in row])
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = (
                f"A1:{get_column_letter(len(payload['headers']))}{len(payload['rows']) + 1}"
            )
            for cell in sheet[1]:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            sheet.row_dimensions[1].height = 28
            for index, header in enumerate(payload["headers"], start=1):
                width = 60 if header in WIDE_COLUMNS else max(12, min(34, len(header) + 6))
                sheet.column_dimensions[get_column_letter(index)].width = width

        path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(path)
        return {
            "workbook": str(path),
            "bytes": path.stat().st_size,
            "tabs": {tab: len(payload["rows"]) for tab, payload in payloads.items()},
            "total_data_rows": sum(len(payload["rows"]) for payload in payloads.values()),
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the six-tab Google Sheets staging workbook.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "exports" / "FrontierAtlas_submission.xlsx"),
    )
    args = parser.parse_args()
    result = build(Path(args.output))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
