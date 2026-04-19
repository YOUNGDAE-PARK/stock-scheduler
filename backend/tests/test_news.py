def test_collect_global_news_parses_rss(monkeypatch):
    from backend.app.services import news

    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>Fed signals slower rate cuts as chip stocks fall</title>
        <link>https://example.com/fed-chip</link>
        <pubDate>Sat, 18 Apr 2026 08:00:00 GMT</pubDate>
        <description>Markets reassess discount rates.</description>
      </item>
    </channel></rss>
    """

    class FakeResponse:
        text = rss

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(news.httpx, "Client", FakeClient)
    result = news.collect_global_news([], [], [], max_items=1)

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Fed signals slower rate cuts as chip stocks fall"
    assert result["items"][0]["url"] == "https://example.com/fed-chip"
    assert result["items"][0]["source"] in {"Global markets", "Korea market", "US macro", "Semiconductor supply chain"}


def test_global_news_schedule_passes_news_items_to_codex(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.schedule_runner as schedule_runner

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(schedule_runner)
    db.init_db()

    captured = {}

    def fake_collect_global_news(enabled_sources, stocks, interest_areas):
        return {
            "items": [
                {
                    "title": "Treasury yields rise as AI chip demand stays strong",
                    "url": "https://example.com/macro",
                    "source": "test feed",
                    "category": "macro",
                    "published_at": "2026-04-18T08:00:00+00:00",
                    "summary": "Rates and semiconductors matter for portfolio positioning.",
                }
            ],
            "sources": [],
            "errors": [],
            "coverage_note": "test",
        }

    def fake_codex(run_type, target, context):
        captured["context"] = context
        run = db.insert(
            "codex_run",
            {
                "run_type": run_type,
                "target": target,
                "agent_role": "schedule-analysis",
                "prompt_path": "",
                "output_path": "",
                "status": "completed",
                "started_at": db.utc_now(),
                "finished_at": db.utc_now(),
                "error": None,
            },
        )
        report = db.insert(
            "report",
            {
                "report_type": run_type,
                "target": target,
                "title": "투자 관점 글로벌 뉴스",
                "markdown": "# 투자 관점 글로벌 뉴스\n\n## 투자 액션\n- 반도체는 분할 접근.",
                "codex_run_id": run["id"],
                "created_at": db.utc_now(),
            },
        )
        return {"run": run, "report": report, "analysis": {"major_signal_detected": True}}

    monkeypatch.setattr(schedule_runner, "collect_global_news", fake_collect_global_news)
    monkeypatch.setattr(schedule_runner, "run_codex_schedule_analysis", fake_codex)

    schedule = next(item for item in db.list_rows("schedule") if item["name"] == "08:00 글로벌 경제뉴스")
    result = schedule_runner.run_schedule_now(schedule["id"])

    assert result["status"] == "completed"
    assert captured["context"]["global_news"]["items"][0]["title"].startswith("Treasury yields")
    assert "enabled_sources" in captured["context"]


def test_global_news_fallback_reports_orchestrator_error_only():
    from backend.app.services.schedule_runner import _build_report_markdown

    markdown = _build_report_markdown(
        {"name": "08:00 글로벌 경제뉴스", "schedule_type": "global_news_digest", "target_type": "all"},
        [{"ticker": "005930", "market": "KR", "name": "삼성전자"}],
        {"updated": [{"ticker": "005930", "market": "KR", "name": "삼성전자", "price": 80000}], "failed": []},
        "codex missing",
        {
            "items": [
                {
                    "title": "AI chip demand rises while Treasury yields stay high",
                    "url": "https://example.com/ai-chip",
                    "source": "test feed",
                    "published_at": "2026-04-18T08:00:00+00:00",
                    "summary": "",
                }
            ]
        },
    )

    assert "## 오류 내용" in markdown
    assert "codex missing" in markdown
    assert "## 최종 투자 관점" not in markdown
    assert "AI chip demand rises" not in markdown
