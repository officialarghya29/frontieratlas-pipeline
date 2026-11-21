from __future__ import annotations

import pytest

from frontieratlas.common.config import HttpSettings
from frontieratlas.common.http import (
    AccessBlockedError,
    AsyncHttpClient,
    PayloadTooLargeError,
    RateLimitedError,
    RetryableHttpError,
)


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"{}", headers: dict | None = None, url: str = "https://example.test/x"):
        self.status = status
        self._body = body
        self.headers = headers or {}
        self.url = url

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls = 0
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def http_settings(retries: int = 2) -> HttpSettings:
    return HttpSettings(
        timeout_seconds=5,
        connect_timeout_seconds=5,
        max_retries=retries,
        base_backoff_seconds=0.001,
        max_backoff_seconds=0.005,
        global_concurrency=2,
        per_domain_concurrency=1,
        default_min_interval_seconds=0,
        user_agent="test",
        rate_limits={},
    )


async def test_rate_limit_honours_retry_after_and_retries(monkeypatch):
    monkeypatch.setattr("frontieratlas.common.http.random.uniform", lambda a, b: 0.0)
    session = FakeSession(
        [
            FakeResponse(429, headers={"retry-after": "0"}),
            FakeResponse(200, body=b'{"ok": true}'),
        ]
    )
    client = AsyncHttpClient(http_settings(), session=session)  # type: ignore[arg-type]
    response = await client.get("https://example.test/data")
    assert response.status == 200
    assert response.json() == {"ok": True}
    assert session.calls == 2
    await client.close()


async def test_413_is_not_retried():
    session = FakeSession([FakeResponse(413)])
    client = AsyncHttpClient(http_settings(), session=session)  # type: ignore[arg-type]
    with pytest.raises(PayloadTooLargeError):
        await client.get("https://example.test/large")
    assert session.calls == 1
    await client.close()


async def test_403_is_not_retried_or_bypassed():
    session = FakeSession([FakeResponse(403)])
    client = AsyncHttpClient(http_settings(), session=session)  # type: ignore[arg-type]
    with pytest.raises(AccessBlockedError):
        await client.get("https://example.test/blocked")
    assert session.calls == 1
    await client.close()


async def test_server_errors_exhaust_bounded_retries(monkeypatch):
    monkeypatch.setattr("frontieratlas.common.http.random.uniform", lambda a, b: 0.0)
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(500)])
    client = AsyncHttpClient(http_settings(retries=2), session=session)  # type: ignore[arg-type]
    with pytest.raises(RetryableHttpError):
        await client.get("https://example.test/fail")
    assert session.calls == 3
    await client.close()


async def test_rate_limit_exhaustion_raises(monkeypatch):
    monkeypatch.setattr("frontieratlas.common.http.random.uniform", lambda a, b: 0.0)
    session = FakeSession(
        [
            FakeResponse(429, headers={"retry-after": "0"}),
            FakeResponse(429, headers={"retry-after": "0"}),
        ]
    )
    client = AsyncHttpClient(http_settings(retries=1), session=session)  # type: ignore[arg-type]
    with pytest.raises(RateLimitedError):
        await client.get("https://example.test/data")
    await client.close()
