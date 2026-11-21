# Submission Packet — FrontierAtlas / GraphOne AI Engineer Assessment

The repository is built, collected, validated, preflight-clean and pushed under **Arghya Bose**. Three account-gated steps remain: **publish the corrected workbook as a public Google Sheet**, optionally **run LLM extraction with your own provider key**, and **submit the form**. The public Sheet URL is the only value that must never be guessed, left as a placeholder, or replaced with a GitHub/XLSX link.

## A. Final links to submit

| Field | Value |
| --- | --- |
| GitHub repository | `https://github.com/officialarghya29/frontieratlas-pipeline` |
| Public Google Sheet | **PENDING — replace after section C; do not submit this literal text** |
| Architecture PDF | `https://github.com/officialarghya29/frontieratlas-pipeline/blob/main/architecture.pdf` |
| Submission form | `https://forms.gle/3JJhukomumTFueRW7` |

Do **not** submit the XLSX link as the Google Sheet URL. The XLSX is the upload source; the Sheet URL must be the `docs.google.com/spreadsheets/...` link after step C.

**A packet that still says PENDING is not final.** Replace both placeholders with the same public Sheet URL after step C. The corrected workbook is `data/exports/FrontierAtlas_submission.xlsx` (6 auto-matched, 71 review-required, 2,413 no-match). Any earlier upload made from an older workbook must be deleted or replaced; do not leave the old mapping counts public.

## B. Copy-paste answers

### Short version

> A reproducible async Python pipeline that collected 1,894 genuine AI startups, 2,490 AI products, 1,314 arXiv papers, 214 publication-verified AI/tech jobs and 16 fresh AI news articles, with GitHub star enrichment, auditable entity resolution (2,490 logged decisions), SQLite persistence, six-tab exports, 53 passing tests and a three-page architecture document. The corrected six-tab workbook is ready to upload; the public Sheet URL is pending because no Google credentials were supplied. LLM orchestration is implemented with Gemini→Groq→DeepSeek fallback and remains pending only because no provider key was supplied.

### Full version, numbered

1. **GitHub repository:** https://github.com/officialarghya29/frontieratlas-pipeline
2. **Public Google Sheet:** **PENDING — replace after section C**
3. **Startup records:** 1,894 unique (1,906 YC AI companies discovered, 12 duplicates removed).
4. **Product records:** 2,490 unique (1,977 Show HN launches, 494 Hugging Face Spaces, 19 Product Hunt launches).
5. **Research paper records:** 1,314 unique arXiv papers across cs.AI, cs.LG, cs.CL, cs.CV and cs.RO.
6. **Job records:** 214 with timezone-aware publication timestamps inside the strict 24-hour window (Himalayas 43, Arbeitnow 107, Jobicy 64).
7. **News records:** 16 inside the 24-hour window (TechCrunch 5, The Verge 4, WIRED 4, Ars Technica 1, MIT Technology Review 2).
8. **Entity mapping records:** 2,490 (6 auto-matched, 71 flagged for manual review, 2,413 no-match).
9. **Data sources:** YC-OSS AI JSON, arXiv API, Product Hunt Atom feed, Hacker News Show HN via Algolia, Hugging Face Spaces API, five RSS feeds (TechCrunch AI, The Verge AI, WIRED AI, Ars Technica, MIT Technology Review), five job-board APIs (Himalayas, Remotive, Remote OK, Arbeitnow, Jobicy), and the GitHub REST API for stars. Papers with Code was disabled because the service was archived; AI Dev Jobs was excluded after it returned zero live listings.
10. **LLM providers implemented:** Gemini Flash → Groq Llama → DeepSeek, with structured JSON extraction, semantic chunking, 413 splitting, 429 Retry-After/backoff, provider fallback and circuit breaking. No provider key was supplied, so extraction is marked pending and no field was guessed.
11. **Database:** SQLite in WAL mode with PostgreSQL-compatible DDL, stable text primary keys, unique constraints, idempotent upserts, revision audit, checkpoints and source-run metadata. PostgreSQL plus queued distributed workers is documented as the 500k-scale migration path, not claimed as implemented.
12. **Tests executed:** `53 passed, 0 failed, 0 errors` via pytest with mocked HTTP (schemas, timezones, 24h freshness, URL normalization, entity matching, dedupe, GitHub enrichment, pagination, retries, 413/429, provider fallback, Sheets mapping).
13. **Architecture PDF:** 3 pages, verified programmatically with pypdf.
14. **Implemented versus proposed:** implemented = async collection, pacing, retries, checkpoints, raw retention, cross-source dedupe before write, strict schemas, idempotent storage, GitHub enrichment, auditable entity resolution, LLM fallback/chunking/backoff, six CSVs + JSONL, Google Sheets exporter and six-tab workbook, quality report, 53 tests, 3-page PDF. Proposed = PostgreSQL cluster, durable queue, distributed workers, 500k throughput validation, graph/vector derived indexes, manual-review UI.
15. **Remaining limitations:** Google Sheet requires your upload/share step; LLM extraction requires your API key; Remotive and Remote OK had no 24h-verifiable listings at run time; product pricing is mostly `UNKNOWN` because pricing facts were not explicitly available; entity association is deliberately conservative; 164/170 explicit GitHub repositories were enriched and the rest remain null; 500k throughput is not claimed.
16. **Reproduction commands:**

```bash
git clone https://github.com/officialarghya29/frontieratlas-pipeline.git
cd frontieratlas-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-deps
cp .env.example .env

python scripts/collect_all.py
python scripts/enrich_github.py --limit 400
python scripts/resolve_entities.py
python scripts/extract_llm.py --limit 25
python scripts/export_all.py
python scripts/validate_all.py
python scripts/build_submission_workbook.py
pytest
python scripts/build_architecture_pdf.py
python scripts/verify_submission.py
```

## C. Publish the Google Sheet (about 3 minutes, under your identity)

The repo contains a styled six-tab workbook: `data/exports/FrontierAtlas_submission.xlsx`. It is also downloadable from GitHub:

`https://github.com/officialarghya29/frontieratlas-pipeline/blob/main/data/exports/FrontierAtlas_submission.xlsx`

The credential-free Sheets dry run validated all six tabs and **8,418 data rows** with **zero secret findings**. Only Google account authorization is missing.

> **Replacement warning:** use this newly regenerated workbook. If you already uploaded an older copy, delete it or overwrite it and use the new URL. The corrected file has **6 auto-matched, 71 review-required and 2,413 no-match** mapping decisions; do not leave an older upload public.

1. Download that file.
2. Go to `https://drive.google.com` → **New** → **File upload** → select the XLSX.
3. Right-click the uploaded file → **Open with** → **Google Sheets**. If prompted, choose **Save as Google Sheets**.
4. Rename it to `FrontierAtlas — AI Ecosystem Dataset`.
5. Click **Share** → **General access** → **Anyone with the link** → **Viewer** → **Copy link**.
6. Check the six tabs and row counts:
   - Startups: 1,894
   - Products: 2,490
   - Research Papers: 1,314
   - Jobs: 214
   - News: 16
   - Entity Mapping Log: 2,490 (6 auto-matched, 71 review-required, 2,413 no-match)
7. Paste the `https://docs.google.com/spreadsheets/d/...` link into the submission form and into item 2 above.
8. Open the copied link in an incognito window. Confirm it opens without sign-in, shows all six tabs, and the Entity Mapping Log still has 2,490 rows.

### Automatic API path (optional, if you prefer a service account)

1. In Google Cloud Console, create/select a project.
2. Enable **Google Sheets API** and **Google Drive API**.
3. Create a service account, create a JSON key, and store it outside this repository.
4. Run:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/service-account.json"
python scripts/export_sheets.py
```

The script creates the spreadsheet, writes all six tabs, freezes headers, adds filters, scans for credential-shaped content, grants public viewer access, and prints the Sheet URL. Use `--dry-run` to validate the payload without credentials.

## D. Optional LLM extraction (only if you have a provider key)

No LLM key was supplied, so extraction is currently `pending` and no field was fabricated. A no-key run was also executed: it wrote `data/processed/llm_extraction.json` with status `pending`, `0` attempted, `0` updated, and left every record unchanged. To run it under your key:

```bash
# Free Gemini key: https://aistudio.google.com/apikey
export GEMINI_API_KEY="your-key"

python scripts/extract_llm.py --limit 25
python scripts/export_all.py
python scripts/validate_all.py
python scripts/build_submission_workbook.py
```

The extractor accepts only evidence-backed values that pass schema validation; everything else stays `null`/`UNKNOWN`. If you publish the Sheet after this, the workbook is already refreshed. If you already published it through the API, rerun `python scripts/export_sheets.py` (idempotent: it clears and rewrites the same six tabs).

## E. Preflight before submitting

```bash
python scripts/verify_submission.py
```

Expected final line: `LOCAL SUBMISSION READY: YES`. It checks required files, record targets, all 5,928 schemas, job/news freshness flags, six tab names, manifest file hashes and row counts, workbook headers and row counts, PDF page count, test results, every commit's author/committer identity, AI attribution across all commit messages, repository secret scan, and writes [`data/exports/submission_summary.json`](data/exports/submission_summary.json). The latest snapshot has **13 checks and 0 failures**. Missing Google/LLM credentials are reported as external actions, not hidden.

Freshness note: the 24-hour checks apply to the committed collection run dated **2026-11-21**. If you submit on a later date, rerun collection and preflight; do not present this snapshot as live 24-hour data.

## F. Security and identity

- The repository commit is authored **Arghya Bose <officialarghya29@gmail.com>**, with no AI co-author and no AI attribution footer.
- No GitHub token, Google key, API key, `.env`, database or raw response is committed. `.env`, credentials, `data/raw/`, and the SQLite database are git-ignored.
- The GitHub token used during the build was never written to any file; revoke it at the end of the day as planned.
- The Sheet must be publicly viewable only after confirming it contains no private data; the included workbook contains dataset rows, source URLs and entity-matching notes only.
