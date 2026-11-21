#!/usr/bin/env python3
"""Build the flat, easy-to-find submission bundle.

Canonical sources remain in the repository. This folder is intentionally a
small, copy-only snapshot so the owner can attach the PDF, upload the workbook
and read the packet without searching through the project.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "submit files"

COPIES = [
    ("01_ARCHITECTURE.pdf", ROOT / "architecture.pdf"),
    (
        "02_GOOGLE_SHEETS_UPLOAD.xlsx",
        ROOT / "data" / "google_sheets" / "FrontierAtlas_Google_Sheets_Upload.xlsx",
    ),
    ("03_SUBMISSION_PACKET.md", ROOT / "SUBMISSION.md"),
]


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    start = DEST / "00_READ_ME_FIRST.md"
    if not start.is_file():
        raise SystemExit(f"Missing start-here guide: {start}")
    for filename, source in COPIES:
        if not source.is_file():
            raise SystemExit(f"Missing canonical source: {source}")
        shutil.copyfile(source, DEST / filename)
        print(f"copied {source.relative_to(ROOT)} -> submit files/{filename}")
    print(f"Submission bundle ready: {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
