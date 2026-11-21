"""Provider-independent LLM extraction with explicit failure semantics.

Implemented behaviour:
* provider order Gemini -> Groq -> DeepSeek, each enabled only when its key exists
* structured JSON output, parsed and schema-checked by the caller
* semantic chunking with paragraph/sentence boundaries and overlap
* 413: split the offending chunk, extract the pieces, merge deterministically
* 429: honour Retry-After, exponential backoff + jitter, then switch provider
* circuit breaking after repeated provider failures
* if every provider fails, return a pending/failed result and keep raw data

No credential is ever read from or written to a file by this module: keys come
from environment variables named in config/settings.yaml.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..common.config import AppSettings, LlmProviderConfig
from ..common.http import (
    AccessBlockedError,
    AsyncHttpClient,
    HttpResponse,
    NetworkError,
    PayloadTooLargeError,
    RateLimitedError,
    RetryableHttpError,
)

SYSTEM_PROMPT = """You are a conservative information extraction engine.

Extract only facts explicitly supported by the provided source content.

Never use outside knowledge to fill missing information.

Never invent dates, names, URLs, employee counts, pricing, authors, repositories or metrics.

If a field is missing or ambiguous, return null.

Return valid JSON matching the supplied schema.

For important non-null fields, include supporting evidence.

If the source does not support the requested entity type, return:
{"valid_entity": false, "reason": "explanation", "record": null}

Do not provide explanations outside the requested JSON output."""

MAX_CHUNK_DEPTH = 3


class AllProvidersFailed(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors[-3:]) or "all providers failed")
        self.errors = errors


@dataclass
class ProviderState:
    config: LlmProviderConfig
    failures: int = 0
    successes: int = 0
    disabled: bool = False
    last_error: str | None = None

    @property
    def name(self) -> str:
        return self.config.name


@dataclass
class ExtractionResult:
    valid_entity: bool
    record: dict | None
    provider: str | None
    attempts: list[dict] = field(default_factory=list)
    chunks: int = 0
    pending_reason: str | None = None
    conflicts: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def chunk_text(text: str, target_chars: int = 12000, overlap_chars: int = 600) -> list[str]:
    """Split text on paragraph/sentence boundaries, preserving all content.

    Chunks are at most ``target_chars`` (except a single unbreakable token) and
    consecutive chunks overlap by up to ``overlap_chars`` characters.
    """

    text = text.strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]

    units = [unit for unit in re.split(r"\n\s*\n", text) if unit.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for unit in units:
        if len(unit) > target_chars:
            flush()
            chunks.extend(_split_long_unit(unit, target_chars))
            continue
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) > target_chars:
            flush()
            overlap = _tail_overlap(chunks[-1] if chunks else "", overlap_chars)
            current = f"{overlap}\n\n{unit}" if overlap else unit
        else:
            current = candidate
    flush()

    if not chunks:
        chunks = [text[:target_chars]]
    return chunks


def _tail_overlap(previous: str, overlap_chars: int) -> str:
    if not previous or overlap_chars <= 0:
        return ""
    tail = previous[-overlap_chars:]
    cut = tail.find(" ")
    if cut > 0:
        tail = tail[cut + 1 :]
    return tail.strip()


def _split_long_unit(unit: str, target_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", unit)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > target_chars:
            chunks.append(sentence[:target_chars])
            sentence = sentence[target_chars:]
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > target_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def split_for_retry(text: str) -> tuple[str, str]:
    """Split an over-large chunk roughly in half at a paragraph or sentence boundary."""

    midpoint = len(text) // 2
    for pattern in (r"\n\s*\n", r"(?<=[.!?])\s+", r"\s+"):
        matches = list(re.finditer(pattern, text))
        if not matches:
            continue
        best = min(matches, key=lambda match: abs(match.start() - midpoint))
        left, right = text[: best.start()].strip(), text[best.end() :].strip()
        if left and right:
            return left, right
    return text[:midpoint], text[midpoint:]


def merge_json_records(records: list[dict]) -> tuple[dict, list[str]]:
    """Deterministic merge across chunks: first non-null wins, lists union, dicts merge, conflicts logged."""

    merged: dict[str, Any] = {}
    conflicts: list[str] = []

    def merge_into(target: dict, source: dict, prefix: str = "") -> None:
        for key, value in source.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in {"evidence", "_evidence"}:
                if isinstance(value, dict):
                    existing = target.setdefault("evidence", {})
                    if isinstance(existing, dict):
                        for evidence_key, evidence_value in value.items():
                            existing.setdefault(evidence_key, evidence_value)
                continue
            if value in (None, "", [], {}):
                continue
            if key not in target:
                target[key] = value
            elif isinstance(target[key], dict) and isinstance(value, dict):
                merge_into(target[key], value, path)
            elif isinstance(target[key], list) and isinstance(value, list):
                for item in value:
                    if item not in target[key]:
                        target[key].append(item)
            elif target[key] != value:
                conflicts.append(path)

    for record in records:
        if isinstance(record, dict):
            merge_into(merged, record)
    return merged, sorted(set(conflicts))


def parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("provider response did not contain a JSON object")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("provider response JSON was not an object")
    return payload


class LLMExtractor:
    def __init__(
        self,
        settings: AppSettings,
        client: AsyncHttpClient,
        *,
        environ: dict[str, str] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.environ = environ if environ is not None else dict(os.environ)
        self._sleep = sleep or asyncio.sleep
        self.providers: list[ProviderState] = [
            ProviderState(config=provider)
            for provider in settings.llm.providers
            if self.environ.get(provider.api_key_env, "").strip()
        ]

    @property
    def available(self) -> bool:
        return any(not provider.disabled for provider in self.providers)

    def health(self) -> list[dict]:
        return [
            {
                "provider": provider.name,
                "disabled": provider.disabled,
                "failures": provider.failures,
                "successes": provider.successes,
                "last_error": provider.last_error,
            }
            for provider in self.providers
        ]

    async def extract(self, content: str, schema_hint: str) -> ExtractionResult:
        if not content.strip():
            return ExtractionResult(False, None, None, pending_reason="empty_content")
        if not self.providers:
            return ExtractionResult(
                False,
                None,
                None,
                pending_reason="no_provider_credentials (set GEMINI_API_KEY, GROQ_API_KEY or DEEPSEEK_API_KEY)",
            )

        chunks = chunk_text(
            content,
            target_chars=self.settings.llm.chunk_target_chars,
            overlap_chars=self.settings.llm.chunk_overlap_chars,
        )
        parsed: list[dict] = []
        attempts: list[dict] = []
        used_provider: str | None = None

        for index, chunk in enumerate(chunks):
            try:
                data, provider = await self._extract_chunk(chunk, schema_hint, depth=0)
            except AllProvidersFailed as exc:
                return ExtractionResult(
                    False,
                    None,
                    used_provider,
                    attempts=attempts,
                    chunks=len(chunks),
                    pending_reason=f"chunk {index + 1}/{len(chunks)} failed: {exc}",
                )
            used_provider = used_provider or provider
            attempts.append({"chunk": index, "provider": provider, "chars": len(chunk)})
            if data:
                parsed.append(data)

        if not parsed:
            return ExtractionResult(
                False, None, used_provider, attempts=attempts, chunks=len(chunks), pending_reason="empty_extraction"
            )

        merged, conflicts = merge_json_records(parsed)
        evidence = merged.get("evidence") if isinstance(merged.get("evidence"), dict) else {}
        if merged.get("valid_entity") is False:
            return ExtractionResult(
                False,
                None,
                used_provider,
                attempts=attempts,
                chunks=len(chunks),
                pending_reason=str(merged.get("reason") or "source does not support the entity"),
                conflicts=conflicts,
                evidence=evidence,
            )
        record = merged.get("record") if isinstance(merged.get("record"), dict) else merged
        return ExtractionResult(
            True,
            record,
            used_provider,
            attempts=attempts,
            chunks=len(chunks),
            conflicts=conflicts,
            evidence=evidence,
        )

    async def _extract_chunk(self, text: str, schema_hint: str, depth: int) -> tuple[dict, str]:
        prompt = f"{schema_hint}\n\nSOURCE CONTENT:\n{text}"
        try:
            raw, provider = await self._with_fallback(prompt)
        except PayloadTooLargeError:
            if depth >= MAX_CHUNK_DEPTH or len(text) < 400:
                raise AllProvidersFailed([f"payload too large after {depth} splits"])
            left, right = split_for_retry(text)
            left_data, provider_left = await self._extract_chunk(left, schema_hint, depth + 1)
            right_data, provider_right = await self._extract_chunk(right, schema_hint, depth + 1)
            merged, _ = merge_json_records([left_data, right_data])
            return merged, provider_left or provider_right
        return parse_json_response(raw), provider

    async def _with_fallback(self, prompt: str) -> tuple[str, str]:
        errors: list[str] = []
        for state in self.providers:
            if state.disabled:
                continue
            for attempt in range(self.settings.llm.max_retries_per_provider + 1):
                try:
                    raw = await self._call_provider(state, prompt)
                    state.failures = 0
                    state.successes += 1
                    return raw, state.name
                except PayloadTooLargeError:
                    raise
                except RateLimitedError as exc:
                    wait = exc.retry_after if exc.retry_after is not None else self._backoff(attempt)
                    state.last_error = f"429 retry-after={wait:.1f}s"
                    await self._sleep(min(wait, self.settings.llm.retry_max_seconds) + random.uniform(0, 0.25))
                    errors.append(f"{state.name}:429")
                except (RetryableHttpError, NetworkError, AccessBlockedError, ValueError, KeyError) as exc:
                    state.last_error = f"{type(exc).__name__}: {exc}"[:200]
                    await self._sleep(self._backoff(attempt))
                    errors.append(f"{state.name}:{type(exc).__name__}")
            state.failures += 1
            if state.failures >= self.settings.llm.circuit_break_after_failures:
                state.disabled = True
        raise AllProvidersFailed(errors)

    def _backoff(self, attempt: int) -> float:
        base = self.settings.llm.retry_base_seconds * (2**attempt)
        return min(base * (1 + random.uniform(0, 0.5)), self.settings.llm.retry_max_seconds)

    async def _call_provider(self, state: ProviderState, prompt: str) -> str:
        config = state.config
        api_key = self.environ.get(config.api_key_env, "").strip()
        model = self.environ.get(config.model_env, "").strip() or config.default_model

        if config.name == "gemini":
            url = config.endpoint.format(model=model)
            headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
            payload = {
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            }
        else:
            url = config.endpoint
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            }

        response: HttpResponse = await self.client.post_json(
            url, json_body=payload, headers=headers, retries=0, raw_label=f"llm-{config.name}"
        )
        body = response.json()
        if config.name == "gemini":
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        else:
            text = body["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty completion")
        return text
