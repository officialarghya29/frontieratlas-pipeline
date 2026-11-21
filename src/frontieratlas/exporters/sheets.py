"""Google Sheets export with six tabs, formatting, idempotency, and public sharing.

Credentials are read from GOOGLE_APPLICATION_CREDENTIALS (a service-account
JSON key path) and never from the repository. If credentials are absent the
caller is told exactly what remains; CSV/JSONL exports are still complete.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..common.config import AppSettings
from ..common.text import remove_control_chars
from ..exporters.datasets import TAB_TYPES, headers_for, rows_for
from ..quality.safety import scan_rows
from ..storage.db import Database

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CELL_CHAR_LIMIT = 4000


class MissingCredentials(RuntimeError):
    pass


def _cell(value: Any) -> Any:
    if isinstance(value, str):
        value = remove_control_chars(value)
        if len(value) > CELL_CHAR_LIMIT:
            return value[: CELL_CHAR_LIMIT - 1] + "…"
    return value


def build_payloads(settings: AppSettings, db: Database) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for record_type in TAB_TYPES:
        if record_type == "ENTITY_MAPPING":
            tab = settings.sheets.tabs.get("ENTITY_MAPPING", "Entity Mapping Log")
            records = db.fetch_mappings()
        else:
            tab = settings.tab_name(record_type)
            records = db.fetch_records(record_type)
        headers = headers_for(record_type)
        rows = [[_cell(value) for value in row] for row in rows_for(record_type, records)]
        payloads[tab] = {"headers": headers, "rows": rows, "record_type": record_type}
    return payloads


def _a1(tab: str, suffix: str = "A1") -> str:
    return f"'{tab.replace(chr(39), chr(39) * 2)}'!{suffix}"


def _credentials():
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not path:
        raise MissingCredentials("GOOGLE_APPLICATION_CREDENTIALS is not set")
    key_path = Path(path)
    if not key_path.exists():
        raise MissingCredentials(f"service-account file not found: {key_path}")
    return service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)


def _services():
    credentials = _credentials()
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return sheets, drive


def scan_payloads(payloads: dict[str, dict]) -> list[str]:
    findings = scan_rows([payload["headers"] for payload in payloads.values()])
    findings += scan_rows([row for payload in payloads.values() for row in payload["rows"]])
    return sorted(set(findings))


def export_to_sheets(settings: AppSettings, db: Database, *, share_public: bool = True) -> dict:
    payloads = build_payloads(settings, db)
    findings = scan_payloads(payloads)
    if findings:
        raise ValueError(f"refusing to publish: credential-shaped content found: {', '.join(findings)}")

    sheets, drive = _services()
    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    created = False

    if not spreadsheet_id:
        body = {
            "properties": {"title": settings.sheets.spreadsheet_title, "locale": "en_US"},
            "sheets": [{"properties": {"title": tab}} for tab in payloads],
        }
        spreadsheet = sheets.spreadsheets().create(body=body, fields="spreadsheetId,sheets").execute()
        spreadsheet_id = spreadsheet["spreadsheetId"]
        created = True

    metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    existing = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in metadata.get("sheets", [])}
    missing = [tab for tab in payloads if tab not in existing]
    if missing:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab}}} for tab in missing]},
        ).execute()
        metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
        existing = {sheet["properties"]["title"]: sheet["properties"]["sheetId"] for sheet in metadata.get("sheets", [])}

    # Idempotent export: clear the six managed tabs before rewriting them.
    sheets.spreadsheets().values().batchClear(
        spreadsheetId=spreadsheet_id,
        body={"ranges": [_a1(tab, "A1:ZZZ100000") for tab in payloads]},
    ).execute()

    # One request per tab keeps each payload well below the Sheets request limit.
    for tab, payload in payloads.items():
        values = [payload["headers"]] + payload["rows"]
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=_a1(tab),
            valueInputOption="RAW",
            body={"majorDimension": "ROWS", "values": values},
        ).execute()

    format_requests: list[dict] = []
    for tab, payload in payloads.items():
        sheet_id = existing[tab]
        format_requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )
        format_requests.append(
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.93, "green": 0.95, "blue": 0.99},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            }
        )
        format_requests.append(
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max(1, len(payload["rows"]) + 1),
                            "startColumnIndex": 0,
                            "endColumnIndex": max(1, len(payload["headers"])),
                        }
                    }
                }
            }
        )
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": format_requests}
    ).execute()

    published = False
    public_error: str | None = None
    if share_public:
        try:
            drive.permissions().create(
                fileId=spreadsheet_id,
                body={"type": "anyone", "role": "reader"},
                fields="id",
            ).execute()
            published = True
        except HttpError as exc:  # permission failure must be reported, not hidden
            public_error = str(exc)
    else:
        public_error = "public sharing disabled by flag"

    share_with = os.environ.get("GOOGLE_SHEETS_SHARE_WITH", "").strip()
    shared_with: str | None = None
    share_error: str | None = None
    if share_with:
        try:
            drive.permissions().create(
                fileId=spreadsheet_id,
                body={"type": "user", "role": "writer", "emailAddress": share_with},
                sendNotificationEmail=False,
                fields="id",
            ).execute()
            shared_with = share_with
        except HttpError as exc:
            share_error = str(exc)

    return {
        "spreadsheet_id": spreadsheet_id,
        "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "created": created,
        "public": published,
        "public_error": public_error,
        "shared_with": shared_with,
        "share_error": share_error,
        "tabs": {tab: {"rows": len(payload["rows"]), "columns": len(payload["headers"])} for tab, payload in payloads.items()},
    }
