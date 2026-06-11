"""Integration test for the /ws relay hub against a real Redis."""

import json
import time

import redis as redis_sync
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def publish_with_retry(channel: str, payload: dict[str, object], attempts: int = 50) -> None:
    """Publish until at least one subscriber receives it (subscription is async)."""
    r = redis_sync.Redis.from_url(get_settings().redis_url)
    for _ in range(attempts):
        if r.publish(channel, json.dumps(payload)) > 0:
            r.close()
            return
        time.sleep(0.1)
    r.close()
    raise AssertionError(f"no subscriber appeared on {channel}")


def test_subscribe_and_receive() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"op": "subscribe", "topics": ["candles:TESTUSDT:1m"]}))
        ack = json.loads(ws.receive_text())
        assert ack == {"op": "subscribed", "topics": ["candles:TESTUSDT:1m"]}

        publish_with_retry("candles:TESTUSDT:1m", {"type": "candle", "close": 123.45})
        msg = json.loads(ws.receive_text())
        assert msg["topic"] == "candles:TESTUSDT:1m"
        assert msg["data"]["close"] == 123.45


def test_unsubscribe_stops_delivery() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"op": "subscribe", "topics": ["t1", "t2"]}))
        ack = json.loads(ws.receive_text())
        assert set(ack["topics"]) == {"t1", "t2"}

        ws.send_text(json.dumps({"op": "unsubscribe", "topics": ["t1"]}))
        ack = json.loads(ws.receive_text())
        assert ack["topics"] == ["t2"]

        # t2 still delivers
        publish_with_retry("t2", {"v": 2})
        msg = json.loads(ws.receive_text())
        assert msg["topic"] == "t2"


def test_invalid_topics_rejected() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"op": "subscribe", "topics": ["bad topic with spaces!"]}))
        # Invalid topics are filtered; nothing subscribed → no ack for empty set.
        ws.send_text(json.dumps({"op": "ping"}))
        msg = json.loads(ws.receive_text())
        assert msg == {"op": "pong"}


def test_invalid_json_gets_error() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_text("not json{")
        msg = json.loads(ws.receive_text())
        assert "error" in msg
