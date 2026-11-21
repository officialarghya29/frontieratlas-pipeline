"""Text, URL, hashing and identifier helpers shared by all pipeline stages."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
    "guccounter",
    "guce_referrer",
    "guce_referrer_sig",
}

LEGAL_SUFFIX_TOKENS = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "co",
    "company",
    "gmbh",
    "ag",
    "sa",
    "sas",
    "bv",
    "nv",
    "plc",
    "pte",
    "pty",
    "oy",
    "ab",
    "as",
    "kft",
    "srl",
    "spa",
    "kk",
    "holdings",
    "group",
}

_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NON_WORD_RE = re.compile(r"[^0-9a-z ]+")
_GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.IGNORECASE)


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    soup = BeautifulSoup(value, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    text = soup.get_text(" ", strip=True)
    text = _WHITESPACE_RE.sub(" ", html.unescape(text)).strip()
    return remove_control_chars(text) or None


def remove_control_chars(value: str) -> str:
    """Remove XML/Sheets-illegal control characters without altering visible text."""

    return _CONTROL_RE.sub("", value)


def normalize_unicode(value: str) -> str:
    return unicodedata.normalize("NFKD", value)


def normalize_name(value: str | None) -> str:
    """Case-folded, punctuation-free, whitespace-free entity name for matching."""

    if not value:
        return ""
    text = normalize_unicode(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"['’`]", "", text)
    text = text.replace("+", " plus ")
    text = _NON_WORD_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def name_key(value: str | None) -> str:
    """Normalized name with trailing legal suffixes removed for candidate matching."""

    tokens = normalize_name(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    text = url.strip()
    if not text:
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"}:
        return text
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QUERY_PARAMS and not k.lower().startswith("utm_")
    ]
    query_pairs.sort()
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit(("https", host + port, path, query, ""))


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    text = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    try:
        host = urlsplit(text).hostname
    except ValueError:
        return None
    return host.lower().removeprefix("www.") if host else None


def stable_id(*parts: object, prefix: str = "fa") -> str:
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def sha256_hex(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def content_hash(payload: object) -> str:
    dumped = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return sha256_hex(dumped)


def truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned or None
    return cleaned[: limit - 1].rstrip() + "…"


def collapse_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    return _WHITESPACE_RE.sub(" ", remove_control_chars(value)).strip() or None


def extract_github_urls(*texts: str | None) -> list[str]:
    """Extract explicitly written GitHub repository URLs from source text.

    This is deliberately conservative: only URLs literally present in the paper
    abstract or arXiv comment field are accepted. Repositories are never guessed
    from paper titles.
    """

    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in _GITHUB_RE.findall(text):
            cleaned = match.rstrip(".,;:)]}'\"")
            cleaned = re.sub(r"\.git$", "", cleaned)
            if cleaned not in found:
                found.append(cleaned)
    return found


def keyword_match(text: str | None, keywords: list[str] | tuple[str, ...]) -> bool:
    if not text:
        return False
    haystack = f" {normalize_name(text)} "
    for keyword in keywords:
        needle = normalize_name(keyword)
        if not needle:
            continue
        if f" {needle} " in haystack:
            return True
    return False


def sanitize_slug(value: str, limit: int = 60) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", normalize_name(value)).strip("-")
    return (clean[:limit] or "unknown").strip("-")
