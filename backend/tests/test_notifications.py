import importlib

from fastapi.testclient import TestClient


def make_client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("NOTIFICATION_MODE", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.main as main

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(main)
    return TestClient(main.app)


def test_telegram_notification_sends_and_records_log(monkeypatch, tmp_path):
    import backend.app.services.notifications as notifications

    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})

        class Response:
            status_code = 200

            def json(self):
                return {"ok": True, "result": {"message_id": 7}}

        return Response()

    monkeypatch.setattr(notifications.httpx, "post", fake_post)

    with make_client(monkeypatch, tmp_path) as client:
        response = client.post("/api/notifications/test", json={"body": "Telegram test"})

    assert response.status_code == 200
    body = response.json()
    assert body["channel"] == "telegram"
    assert body["status"] == "sent"
    assert body["error"] is None
    assert calls[0]["url"] == "https://api.telegram.org/bottest-token/sendMessage"
    assert calls[0]["json"]["chat_id"] == "123456"
    assert "Telegram test" in calls[0]["json"]["text"]


def test_telegram_notification_splits_long_report(monkeypatch, tmp_path):
    import backend.app.services.notifications as notifications

    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})

        class Response:
            status_code = 200

            def json(self):
                return {"ok": True, "result": {"message_id": len(calls)}}

        return Response()

    monkeypatch.setattr(notifications.httpx, "post", fake_post)

    long_report = "\n".join(f"- line {index} " + "x" * 120 for index in range(120))

    with make_client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/api/notifications/test",
            json={
                "title": "긴 리포트",
                "body": "전문 전송",
                "payload": {"report_id": 1, "report_markdown": long_report},
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert len(calls) > 1
    assert all(len(call["json"]["text"]) <= notifications.TELEGRAM_MAX_MESSAGE_LENGTH + 10 for call in calls)
    combined = "\n".join(call["json"]["text"] for call in calls)
    assert "----- 리포트 본문 -----" in combined
    assert "- line 119" in combined
