# README asset index

Every visual in this folder is generated from the committed FrontierAtlas run. There are no stock photos and no hand-typed chart values.

| Asset | What it shows | Source |
| --- | --- | --- |
| `00_hero_signal_map.png` | Abstract signal-map hero with the run totals | `data_quality_report.json` |
| `01_dataset_at_a_glance.png` | Records by artifact type | `counts.by_type` |
| `02_source_yield_comparison.png` | Accepted / discovered yield for all 15 sources | `sources[]` |
| `03_entity_resolution_split.png` | Auto / review / no-match split and method counts | `entity_resolution` |
| `04_freshness_window.png` | Publication age of every accepted job and news item | `jobs.csv`, `news.csv` |
| `05_targets_vs_actual.png` | Assignment targets compared with actual output | `targets` |
| `06_startup_industry_mix.png` | YC AI startup industry distribution | `startups.csv` |
| `07_pipeline_architecture.png` | Implemented pipeline boundaries | repository modules |
| `08_workbook_map.png` | Six tabs and reconciliation totals for the workbook | `data_quality_report.json` |
| `09_workbook_startups_preview.png` | Readable crop of the actual Startups tab | `FrontierAtlas_submission.xlsx` |
| `09_workbook_full_page.png` | Full first-page workbook render | `FrontierAtlas_submission.xlsx` |
| `10_architecture_page_preview.png` | Rendered page 1 of the architecture PDF | `architecture.pdf` |

## Rebuild

```bash
pip install -r requirements-dev.txt
python scripts/build_readme_assets.py
```

The chart set needs `matplotlib` and `Pillow`. The two screenshot renders also need `libreoffice` and `pdftoppm`; if either is missing, the script still rebuilds the charts and skips the screenshots.

The workbook and per-tab CSV copies are rebuilt separately:

```bash
python scripts/build_sheet_imports.py
```

That writes `data/google_sheets/` with one XLSX, six numbered CSVs and `tab_manifest.json`.
