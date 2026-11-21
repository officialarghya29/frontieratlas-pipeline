"""Refuse to publish exports that contain credential-shaped strings."""

from __future__ import annotations

import os
import re
from typing import Iterable

SECRET_PATTERNS = {
    "github_classic_token": re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    "github_fine_grained_token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._-]{30,}\b"),
}


def scan_text(text: str) -> list[str]:
    findings = [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
    for env_name in ("GITHUB_TOKEN", "GEMINI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if len(value) >= 20 and value in text:
            findings.append(f"environment_value:{env_name}")
    return sorted(set(findings))


def scan_rows(rows: Iterable[Iterable[object]]) -> list[str]:
    findings: set[str] = set()
    for row in rows:
        for cell in row:
            if cell is None:
                continue
            findings.update(scan_text(str(cell)))
    return sorted(findings)
