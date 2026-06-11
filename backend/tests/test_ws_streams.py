import asyncio
from types import TracebackType
from typing import Any

import pytest

from app.ingestion import ws_streams
from app.ingestion.ws_streams import BackoffPolicy, consume_stream


class FakeWS:
    def __init__(self, messages: list[str]) -> None:
        self._messages = iter(messages)

    async def __aenter__(self) -> "FakeWS":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def recv(self) -> str:
        try:
            return next(self._messages)
        except StopIteration:
            raise ConnectionError("connection closed") from None


@pytest.mark.asyncio
async def test_consume_stream_reconnects_after_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    connections: list[str] = []

    def fake_connect(url: str, **kwargs: Any) -> FakeWS:
        connections.append(url)
        if len(connections) == 1:
            return FakeWS(['{"seq": 1}'])  # drops after one message
        return FakeWS(['{"seq": 2}'])

    monkeypatch.setattr(ws_streams.websockets, "connect", fake_connect)

    received: list[dict[str, Any]] = []
    stop = asyncio.Event()

    async def handler(msg: dict[str, Any]) -> None:
        received.append(msg)
        if len(received) >= 2:
            stop.set()

    await asyncio.wait_for(
        consume_stream(
            "wss://fake/stream",
            handler,
            name="test",
            backoff=BackoffPolicy(base=0.01, cap=0.01),
            stop_event=stop,
        ),
        timeout=5.0,
    )
    assert [m["seq"] for m in received] == [1, 2]
    assert len(connections) == 2  # reconnected exactly once


def test_backoff_grows_exponentially_and_caps() -> None:
    policy = BackoffPolicy(base=1.0, cap=60.0)
    delays = [policy.next_delay() for _ in range(8)]
    assert delays[:4] == [1.0, 2.0, 4.0, 8.0]
    assert max(delays) == 60.0
    assert delays[-1] == 60.0


def test_backoff_resets_after_success() -> None:
    policy = BackoffPolicy(base=1.0, cap=60.0)
    policy.next_delay()
    policy.next_delay()
    policy.reset()
    assert policy.next_delay() == 1.0
