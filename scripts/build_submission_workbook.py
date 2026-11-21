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
from openpyxl.worksheet.properties import PageSetupProperties

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frontieratlas.common.config import get_settings  # noqa: E402
from frontieratlas.common.text import remove_control_chars  # noqa: E402
from frontieratlas.exporters.sheets import build_payloads, scan_payloads  # noqa: E402
from frontieratlas.storage.db import Database  # noqa: E402

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=9.5)
HEADER_ALIGNMENT = Alignment(vertical="center", horizontal="left", wrap_text=True)
DATA_ALIGNMENT = Alignment(vertical="top", horizontal="left", wrap_text=True)
FORMULA_PREFIXES = ("=", "+", "-", "@")
DATA_ROW_HEIGHT = 42
HEADER_ROW_HEIGHT = 42

# Explicit widths keep identifiers and URLs readable without spilling into the
# next column. Long prose columns stay wide but wrap inside their cells.
COLUMN_WIDTHS = {
    "schemaVersion": 13,
    "recordType": 14,
    "record_id": 30,
    "source_name": 30,
    "source_url": 42,
    "entityName": 32,
    "employeeCount": 13,
    "website": 38,
    "description": 58,
    "foundedYear": 12,
    "industry": 22,
    "headquarters": 26,
    "recordUrl": 42,
    "startupName": 26,
    "pricingModel": 14,
    "productUrl": 42,
    "category": 24,
    "title": 45,
    "authors": 38,
    "paper_url": 40,
    "github_url": 40,
    "github_stars": 13,
    "github_checked_at": 21,
    "published_date": 21,
    "abstract": 58,
    "githubEvidenceUrl": 40,
    "company": 28,
    "date": 21,
    "is_remote": 11,
    "role_family": 16,
    "job_url": 42,
    "dateEvidence": 38,
    "freshness_verified": 17,
    "publisher": 24,
    "full_text": 58,
    "summary": 55,
    "article_url": 42,
    "extraction_status": 18,
    "collectedAt": 21,
    "raw_name": 35,
    "canonical_name": 30,
    "entity_type": 15,
    "method": 22,
    "similarity_score": 16,
    "decision": 18,
    "review_required": 16,
    "mapped_at": 21,
    "notes": 48,
}


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
                cell.alignment = HEADER_ALIGNMENT
            sheet.row_dimensions[1].height = HEADER_ROW_HEIGHT
            for index, header in enumerate(payload["headers"], start=1):
                width = COLUMN_WIDTHS.get(header, max(12, min(34, len(header) + 6)))
                sheet.column_dimensions[get_column_letter(index)].width = width
            for row_index, row in enumerate(
                sheet.iter_rows(min_row=2, max_row=len(payload["rows"]) + 1, max_col=len(payload["headers"])),
                start=2,
            ):
                for cell in row:
                    cell.alignment = DATA_ALIGNMENT
                sheet.row_dimensions[row_index].height = DATA_ROW_HEIGHT
            sheet.print_title_rows = "1:1"
            sheet.page_setup.orientation = "landscape"
            sheet.page_setup.fitToWidth = 1
            sheet.page_setup.fitToHeight = 0
            sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

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
