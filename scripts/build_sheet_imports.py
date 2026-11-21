#!/usr/bin/env python3
"""Create a self-contained Google Sheets handoff folder.

The canonical exports stay in data/exports/. This folder is a convenience copy:
one uploadable XLSX, six numbered CSVs for manual tab imports, and a manifest
that records the exact row counts and headers of each tab.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "data" / "exports"
DEST = ROOT / "data" / "google_sheets"

TABS = [
    ("01_Startups.csv", "startups.csv", "Startups"),
    ("02_Products.csv", "products.csv", "Products"),
    ("03_Research_Papers.csv", "research_papers.csv", "Research Papers"),
    ("04_Jobs.csv", "jobs.csv", "Jobs"),
    ("05_News.csv", "news.csv", "News"),
    ("06_Entity_Mapping_Log.csv", "entity_mapping_log.csv", "Entity Mapping Log"),
]


def metadata(path: Path) -> tuple[int, list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        headers = next(reader, [])
        rows = sum(1 for _ in reader)
    return rows, headers


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    tabs = []
    for output_name, source_name, tab_name in TABS:
        source = EXPORTS / source_name
        target = DEST / output_name
        shutil.copyfile(source, target)
        rows, headers = metadata(target)
        tabs.append(
            {
                "tab": tab_name,
                "file": output_name,
                "source": f"data/exports/{source_name}",
                "rows": rows,
                "columns": len(headers),
                "headers": headers,
            }
        )

    workbook = EXPORTS / "FrontierAtlas_submission.xlsx"
    shutil.copyfile(workbook, DEST / "FrontierAtlas_Google_Sheets_Upload.xlsx")
    manifest = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workbook": "FrontierAtlas_Google_Sheets_Upload.xlsx",
        "total_data_rows": sum(tab["rows"] for tab in tabs),
        "tabs": tabs,
    }
    (DEST / "tab_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
