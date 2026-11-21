# Submit these files

This folder is the short path. It contains the files and links needed for the GraphOne / FrontierAtlas submission, without making you search the rest of the repository.

## The four things to deal with

| # | What | Where |
| --- | --- | --- |
| 1 | **GitHub repository** — paste this URL | <https://github.com/officialarghya29/frontieratlas-pipeline> |
| 2 | **Architecture PDF** — attach this file | `01_ARCHITECTURE.pdf` |
| 3 | **Google Sheets workbook** — upload this to Google Drive | `02_GOOGLE_SHEETS_UPLOAD.xlsx` |
| 4 | **Public Google Sheet URL** — paste after publishing | **PENDING — see steps below** |

The submission packet with longer answers is `03_SUBMISSION_PACKET.md`. The form is here:

<https://forms.gle/3JJhukomumTFueRW7>

> There is no public Google Sheet URL in this folder yet. No URL was invented. The workbook is the file that becomes the Sheet.

## Publish the Sheet in five steps

1. Upload `02_GOOGLE_SHEETS_UPLOAD.xlsx` to Google Drive.
2. Right-click it → **Open with** → **Google Sheets**; save it as a Google Sheet if prompted.
3. Rename it **FrontierAtlas — AI Ecosystem Dataset**.
4. **Share** → **General access** → **Anyone with the link** → **Viewer** → **Copy link**.
5. Open the copied link in an incognito window. It must open without a Google sign-in.

Then put the copied `https://docs.google.com/spreadsheets/d/...` URL into the form. Do **not** paste the XLSX link as the Google Sheet URL.

> **Replace any earlier upload.** The corrected workbook has **6 auto-matched, 71 review-required and 2,413 no-match** entity decisions. An older copy with different counts should be deleted or replaced.

## Verify the workbook before pasting

| Tab | Rows |
| --- | ---: |
| Startups | 1,894 |
| Products | 2,490 |
| Research Papers | 1,314 |
| Jobs | 214 |
| News | 16 |
| Entity Mapping Log | 2,490 |
| **Total data rows** | **8,418** |

The workbook contains six tabs and 8,418 data rows. The six numbered CSVs in `data/google_sheets/` are only for manual tab rebuilding; the XLSX is the fastest path.

## What is in this folder

| File | Purpose |
| --- | --- |
| `00_READ_ME_FIRST.md` | This checklist |
| `01_ARCHITECTURE.pdf` | The three-page architecture document to attach |
| `02_GOOGLE_SHEETS_UPLOAD.xlsx` | The six-tab workbook to upload to Drive |
| `03_SUBMISSION_PACKET.md` | Copy-paste answers and the detailed Sheet instructions |

The copies are generated from the canonical repository files. If the dataset or packet changes, rebuild them with:

```bash
python3 scripts/build_submit_folder.py
```

Canonical sources remain at `architecture.pdf`, `data/google_sheets/FrontierAtlas_Google_Sheets_Upload.xlsx`, and `SUBMISSION.md`.
