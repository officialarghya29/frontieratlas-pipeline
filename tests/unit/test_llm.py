from __future__ import annotations

import json
from dataclasses import replace

from frontieratlas.common.config import get_settings
from frontieratlas.common.http import HttpResponse, PayloadTooLargeError, RateLimitedError, RetryableHttpError
from frontieratlas.extractors.llm import LLMExtractor, chunk_text, merge_json_records, parse_json_response


class FakeLLMClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    async def post_json(self, url, *, json_body, headers=None, retries=None, raw_label=None, **kwargs):
        self.calls.append({"url": url, "body": json_body})
        return self.handler(url, json_body)


async def no_sleep(_seconds: float) -> None:
    return None


def gemini_response(payload: dict) -> HttpResponse:
    body = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps(payload)}]}}
        ]
    }
    return HttpResponse(url="gemini", status=200, headers={}, body=json.dumps(body).encode())


def groq_response(payload: dict) -> HttpResponse:
    body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return HttpResponse(url="groq", status=200, headers={}, body=json.dumps(body).encode())


def test_chunk_text_preserves_all_paragraphs_and_overlaps():
    paragraphs = [f"paragraph-{index} " + ("word " * 120) for index in range(6)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, target_chars=900, overlap_chars=60)
    assert len(chunks) > 1
    combined = " ".join(chunks)
    for index in range(6):
        assert f"paragraph-{index}" in combined
    assert chunks[1].startswith(chunks[0][-60:].split(" ", 1)[-1][:10]) or len(chunks[0]) > 60


def test_merge_json_records_merges_nested_dicts_and_unions_lists():
    merged, conflicts = merge_json_records(
        [
            {"valid_entity": True, "record": {"pricingModel": "FREE", "tags": ["a"]}},
            {"valid_entity": True, "record": {"category": "Tool", "tags": ["b"]}},
        ]
    )
    assert merged["record"]["pricingModel"] == "FREE"
    assert merged["record"]["category"] == "Tool"
    assert merged["record"]["tags"] == ["a", "b"]
    assert conflicts == []


def test_parse_json_response_strips_code_fence():
    assert parse_json_response('```json\n{"valid_entity": true}\n```') == {"valid_entity": True}


async def test_429_backoff_then_success():
    settings = get_settings()
    settings = replace(
        settings,
        llm=replace(settings.llm, max_retries_per_provider=1, retry_base_seconds=0.001, retry_max_seconds=0.01),
    )
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    state = {"first": True}

    def handler(url, body):
        if state["first"]:
            state["first"] = False
            raise RateLimitedError(url, 429, retry_after=0)
        return gemini_response({"valid_entity": True, "record": {"pricingModel": "FREEMIUM"}})

    client = FakeLLMClient(handler)
    extractor = LLMExtractor(
        settings,
        client,  # type: ignore[arg-type]
        environ={"GEMINI_API_KEY": "test-key"},
        sleep=record_sleep,
    )
    result = await extractor.extract("A product description.", "schema")
    assert result.valid_entity is True
    assert result.provider == "gemini"
    assert len(client.calls) == 2
    assert sleeps


async def test_provider_fallback_after_failure():
    settings = get_settings()
    settings = replace(settings, llm=replace(settings.llm, max_retries_per_provider=0))

    def handler(url, body):
        if "generativelanguage" in url:
            raise RetryableHttpError(url, 500, "provider down")
        return groq_response({"valid_entity": True, "record": {"pricingModel": "PAID"}})

    client = FakeLLMClient(handler)
    extractor = LLMExtractor(
        settings,
        client,  # type: ignore[arg-type]
        environ={"GEMINI_API_KEY": "a", "GROQ_API_KEY": "b"},
        sleep=no_sleep,
    )
    result = await extractor.extract("A product description.", "schema")
    assert result.valid_entity is True
    assert result.provider == "groq"
    assert len(client.calls) == 2


async def test_all_providers_failing_returns_pending():
    settings = get_settings()
    settings = replace(settings, llm=replace(settings.llm, max_retries_per_provider=0))

    def handler(url, body):
        raise RetryableHttpError(url, 503, "down")

    extractor = LLMExtractor(
        settings,
        FakeLLMClient(handler),  # type: ignore[arg-type]
        environ={"GEMINI_API_KEY": "a"},
        sleep=no_sleep,
    )
    result = await extractor.extract("A product description.", "schema")
    assert result.valid_entity is False
    assert result.record is None
    assert "failed" in (result.pending_reason or "")


async def test_missing_credentials_never_fabricates():
    settings = get_settings()
    extractor = LLMExtractor(settings, FakeLLMClient(lambda url, body: None), environ={}, sleep=no_sleep)  # type: ignore[arg-type]
    result = await extractor.extract("Some content.", "schema")
    assert result.valid_entity is False
    assert "no_provider_credentials" in (result.pending_reason or "")


async def test_413_splits_chunk_and_merges_results():
    settings = get_settings()
    settings = replace(
        settings,
        llm=replace(settings.llm, chunk_target_chars=500, chunk_overlap_chars=20, max_retries_per_provider=0),
    )
    state = {"first": True}

    def handler(url, body):
        if state["first"]:
            state["first"] = False
            raise PayloadTooLargeError(url, 413, "too large")
        return gemini_response({"valid_entity": True, "record": {"pricingModel": "ENTERPRISE"}})

    content = "\n\n".join(f"paragraph {index} " + ("text " * 80) for index in range(6))
    client = FakeLLMClient(handler)
    extractor = LLMExtractor(
        settings,
        client,  # type: ignore[arg-type]
        environ={"GEMINI_API_KEY": "a"},
        sleep=no_sleep,
    )
    result = await extractor.extract(content, "schema")
    assert result.valid_entity is True
    assert result.record == {"pricingModel": "ENTERPRISE"}
    assert len(client.calls) >= 3
