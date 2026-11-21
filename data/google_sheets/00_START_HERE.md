# FrontierAtlas — Google Sheets handoff

This folder exists so there is no ambiguity about what to upload.

It contains the same six-tab dataset in two formats:

- **One XLSX** — `FrontierAtlas_Google_Sheets_Upload.xlsx`
- **Six numbered CSVs** — one per tab, in the exact tab order

Use the XLSX unless you specifically want to build the Sheet tab by tab. Both paths produce the same six tabs and **8,418 data rows**.

## Folder contents

| File | Google Sheets tab | Data rows | Columns |
| --- | --- | ---: | ---: |
| `FrontierAtlas_Google_Sheets_Upload.xlsx` | all six tabs | 8,418 | — |
| `01_Startups.csv` | Startups | 1,894 | 14 |
| `02_Products.csv` | Products | 2,490 | 13 |
| `03_Research_Papers.csv` | Research Papers | 1,314 | 16 |
| `04_Jobs.csv` | Jobs | 214 | 15 |
| `05_News.csv` | News | 16 | 16 |
| `06_Entity_Mapping_Log.csv` | Entity Mapping Log | 2,490 | 10 |
| `tab_manifest.json` | machine-readable row/column manifest | — | — |

The canonical exports remain in `data/exports/`. This folder is the handoff copy, so there is no need to sort through JSONL or the local database.

## Option A — upload the XLSX (recommended)

1. Download `FrontierAtlas_Google_Sheets_Upload.xlsx` from this folder.
2. Open [Google Drive](https://drive.google.com) while signed in as **Arghya Bose**.
3. Choose **New → File upload** and select the XLSX.
4. Right-click the uploaded file → **Open with → Google Sheets**. If Google asks, choose **Save as Google Sheets**.
5. Rename the spreadsheet to **`FrontierAtlas — AI Ecosystem Dataset`**.
6. Check the bottom tabs in this order:
   - `Startups` — 1,894 rows
   - `Products` — 2,490 rows
   - `Research Papers` — 1,314 rows
   - `Jobs` — 214 rows
   - `News` — 16 rows
   - `Entity Mapping Log` — 2,490 rows
7. Click **Share → General access → Anyone with the link → Viewer → Copy link**.
8. Open the copied link in an incognito window. It must open without a Google sign-in.

> **Do not keep an older upload public.** This workbook contains the corrected entity-resolution pass: **6 auto-matched, 71 review-required, 2,413 no-match**. If you previously uploaded an earlier workbook, delete it or replace it and use the new URL.

## Option B — import the six CSVs

Use this only if you want to rebuild the spreadsheet manually.

1. Create a blank Google Sheet named **`FrontierAtlas — AI Ecosystem Dataset`**.
2. Rename the tabs exactly: `Startups`, `Products`, `Research Papers`, `Jobs`, `News`, `Entity Mapping Log`. Delete the default `Sheet1`.
3. For each tab, click the tab name, then **File → Import → Upload**, choose the matching numbered CSV, and set the import location to **Replace data at selected cell** (cell `A1`).
4. Keep the header row as row 1. The numbered filenames map to the tab order above.
5. Share the Sheet as **Anyone with the link → Viewer** and open the link in an incognito window.

> Google Sheets can display a row-count cap warning near the bottom of very large tabs. The dataset itself is complete in the file; the workbook caps only individual cell text at 4,000 characters. The CSV/JSONL exports in `data/exports/` retain full values.

## What is intentionally not here

There is **no Google Sheet URL** in this folder. The repository has no Google credentials and no Sheet was published by automation. Supplying a real-looking URL would be worse than leaving the handoff explicit. After step 7 or 8, put the URL in:

- `SUBMISSION.md` — section A and item 2
- the GraphOne submission form: <https://forms.gle/3JJhukomumTFueRW7>

## API path, if you prefer automation

The repository also supports a service account:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/service-account.json"
python scripts/export_sheets.py
```

That path creates the spreadsheet, writes the six tabs, scans for credential-shaped content, grants public viewer access and prints the URL. The manual XLSX path is faster if you only need the submission link.

## Verification

The handoff folder was generated from the committed exports and checked against the workbook:

- **8,418 total data rows**
- **six tab names**
- **0 secret findings** in the Sheet payload dry run
- **0 schema issues** in the underlying records

The manifest in `tab_manifest.json` is the source of truth for row and column counts.
