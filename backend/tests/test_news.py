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
    assert result["items"][0]["source"] in {
        "BBC Business",
        "BBC World",
        "The Guardian Business",
        "NPR Business",
        "ABC News Business",
        "Al Jazeera Global",
        "Fortune",
        "Forbes Business",
        "Federal Reserve Press Releases",
        "ECB Press Releases",
    }


def test_pipeline_collection_classification_and_clustering(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.news_pipeline as news_pipeline

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(news_pipeline)
    db.init_db()

    db.insert(
        "interest_area",
        {
            "name": "AI 반도체",
            "category": "research",
            "keywords": ["HBM", "온디바이스 AI"],
            "linked_tickers": ["005930"],
            "memo": "",
            "enabled": True,
        },
    )
    db.insert(
        "interest_stock",
        {
            "ticker": "005930",
            "market": "KR",
            "name": "삼성전자",
            "tags": [],
            "memo": "",
            "enabled": True,
            "alert_settings": {},
        },
    )
    db.insert(
        "holding_stock",
        {
            "ticker": "000660",
            "market": "KR",
            "name": "SK하이닉스",
            "quantity": 2,
            "avg_price": 150000,
            "memo": "",
            "enabled": True,
            "alert_settings": {},
        },
    )

    monkeypatch.setattr(
        news_pipeline,
        "collect_global_news",
        lambda enabled_sources, stocks, interest_areas, max_items=36: {
            "items": [
                {
                    "title": "삼성전자 HBM 수요 확대에 AI 반도체 기대감 상승",
                    "url": "https://example.com/1",
                    "source": "test feed",
                    "category": "sector",
                    "published_at": "2026-04-26T07:00:00+00:00",
                    "summary": "AI 반도체와 HBM 흐름이 강세다.",
                },
                {
                    "title": "SK하이닉스 실적 기대에도 금리 부담 우려",
                    "url": "https://example.com/2",
                    "source": "test feed",
                    "category": "macro",
                    "published_at": "2026-04-26T07:10:00+00:00",
                    "summary": "금리와 실적이 동시에 시장 변수다.",
                },
            ],
            "sources": [],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        news_pipeline,
        "fetch_article_body",
        lambda url: {
            "resolved_url": url,
            "content_type": "text/html",
            "body": "삼성전자와 SK하이닉스가 HBM과 AI 메모리 공급 확대 수혜를 본다."
            if url.endswith("/1")
            else "SK하이닉스 실적과 금리 변수에 대한 본문 설명.",
        },
    )

    collect_result = news_pipeline.run_news_collection()
    fetch_result = news_pipeline.run_article_fetch()
    classify_result = news_pipeline.classify_news()
    cluster_result = news_pipeline.cluster_news()

    assert collect_result["inserted"] == 2
    assert fetch_result["fetched"] == 2
    assert classify_result["inserted"] == 2
    assert cluster_result["inserted"] >= 1

    raw_rows = db.list_rows("news_raw")
    assert any(row["raw_body"] for row in raw_rows)
    refined_rows = db.list_rows("news_refined")
    assert any("005930" in row["tickers"] for row in refined_rows)
    assert any(row["user_links"]["interest_areas"] for row in refined_rows)
    assert any(row["user_links"]["holdings"] for row in refined_rows)


def test_pipeline_collection_uses_initial_backfill_and_then_incremental_cutoff(monkeypatch, tmp_path):
    import importlib
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.news_pipeline as news_pipeline

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(news_pipeline)
    db.init_db()

    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=10)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()
    latest = now.isoformat()

    monkeypatch.setattr(
        news_pipeline,
        "collect_global_news",
        lambda enabled_sources, stocks, interest_areas, max_items=36: {
            "items": [
                {
                    "title": "old item",
                    "url": "https://example.com/old",
                    "source": "test feed",
                    "source_key": "default:test",
                    "category": "macro",
                    "published_at": old,
                    "summary": "too old",
                },
                {
                    "title": "recent item",
                    "url": "https://example.com/recent",
                    "source": "test feed",
                    "source_key": "default:test",
                    "category": "macro",
                    "published_at": recent,
                    "summary": "keep",
                },
            ],
            "sources": [{"feed_id": "default:test", "name": "test feed"}],
            "errors": [],
        },
    )

    first = news_pipeline.run_news_collection()
    assert first["inserted"] == 1
    assert first["filtered_out"] == 1

    state = db.get_pipeline_state("news_collect")
    assert state["meta"]["source_last_collected_at"]["default:test"] == recent

    monkeypatch.setattr(
        news_pipeline,
        "collect_global_news",
        lambda enabled_sources, stocks, interest_areas, max_items=36: {
            "items": [
                {
                    "title": "stale item",
                    "url": "https://example.com/stale",
                    "source": "test feed",
                    "source_key": "default:test",
                    "category": "macro",
                    "published_at": recent,
                    "summary": "already covered",
                },
                {
                    "title": "latest item",
                    "url": "https://example.com/latest",
                    "source": "test feed",
                    "source_key": "default:test",
                    "category": "macro",
                    "published_at": latest,
                    "summary": "new",
                },
            ],
            "sources": [{"feed_id": "default:test", "name": "test feed"}],
            "errors": [],
        },
    )

    second = news_pipeline.run_news_collection()
    assert second["inserted"] == 1
    assert second["filtered_out"] == 1


def test_pipeline_chain_runs_collect_fetch_classify_cluster_in_order(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.news_pipeline as news_pipeline

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(news_pipeline)
    db.init_db()

    calls = []

    monkeypatch.setattr(news_pipeline, "pipeline_is_stale", lambda hours=4: True)
    monkeypatch.setattr(
        news_pipeline,
        "run_news_collection",
        lambda max_items=36: calls.append("collect") or {"status": "completed", "news_raw_ids": [1]},
    )
    monkeypatch.setattr(
        news_pipeline,
        "run_article_fetch",
        lambda limit=24: calls.append("fetch") or {"status": "completed", "news_raw_ids": [1]},
    )
    monkeypatch.setattr(
        news_pipeline,
        "classify_news",
        lambda limit=80: calls.append("classify") or {"status": "completed", "news_refined_ids": [2]},
    )
    monkeypatch.setattr(
        news_pipeline,
        "cluster_news",
        lambda window_hours=24, max_clusters=12: calls.append("cluster") or {"status": "completed", "news_cluster_ids": [3]},
    )

    result = news_pipeline.run_news_pipeline_chain()

    assert calls == ["collect", "fetch", "classify", "cluster"]
    assert result["status"] == "completed"
    assert result["started_from"] == "news_collect"
    assert db.get_pipeline_state("news_collect")["status"] == "completed"
    assert db.get_pipeline_state("article_fetch")["status"] == "completed"
    assert db.get_pipeline_state("news_classify")["status"] == "completed"
    assert db.get_pipeline_state("market_cluster")["status"] == "completed"


def test_pipeline_chain_resumes_from_running_classifier(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.news_pipeline as news_pipeline

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(news_pipeline)
    db.init_db()

    db.upsert_pipeline_state(
        "news_classify",
        {
            "status": "running",
            "last_started_at": db.utc_now(),
            "meta": {"trigger": "test"},
        },
    )

    calls = []
    monkeypatch.setattr(
        news_pipeline,
        "classify_news",
        lambda limit=80: calls.append("classify") or {"status": "completed", "news_refined_ids": [11]},
    )
    monkeypatch.setattr(
        news_pipeline,
        "cluster_news",
        lambda window_hours=24, max_clusters=12: calls.append("cluster") or {"status": "completed", "news_cluster_ids": [12]},
    )

    result = news_pipeline.run_news_pipeline_chain()

    assert calls == ["classify", "cluster"]
    assert result["started_from"] == "news_classify"
    assert db.get_pipeline_state("news_classify")["status"] == "completed"


def test_pipeline_chain_skips_when_already_running(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.news_pipeline as news_pipeline

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(news_pipeline)
    db.init_db()

    acquired = news_pipeline.PIPELINE_RUN_LOCK.acquire(blocking=False)
    assert acquired is True
    try:
        result = news_pipeline.run_news_pipeline_chain(force_collect=True)
    finally:
        news_pipeline.PIPELINE_RUN_LOCK.release()

    assert result["status"] == "skipped"
    assert result["reason"] == "pipeline_running"
    assert result["collect"]["status"] == "skipped"


def test_strategy_context_prefers_refined_news_over_raw_only(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.services.news_pipeline as news_pipeline

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(news_pipeline)
    db.init_db()

    stock = db.insert(
        "interest_stock",
        {
            "ticker": "005930",
            "market": "KR",
            "name": "삼성전자",
            "tags": [],
            "memo": "",
            "enabled": True,
            "alert_settings": {},
        },
    )
    raw = db.insert(
        "news_raw",
        {
            "title": "삼성전자 AI 반도체 기사 원문 제목",
            "url": "https://example.com/article",
            "source": "test feed",
            "category": "sector",
            "published_at": "2026-04-26T07:00:00+00:00",
            "collected_at": db.utc_now(),
            "raw_summary": "원문 요약",
            "raw_body": "기사 본문 원문",
            "content_hash": "hash-1",
            "raw_payload": {},
        },
    )
    db.insert(
        "news_refined",
        {
            "news_raw_id": raw["id"],
            "tickers": ["005930"],
            "sectors": ["ai", "semiconductor"],
            "importance": 4,
            "sentiment": "positive",
            "user_links": {"interest_areas": [], "interest_stocks": [{"id": stock["id"], "ticker": "005930", "name": "삼성전자"}], "holdings": []},
            "refined_summary": "HBM 수요 확대와 AI 반도체 모멘텀이 강화되는 흐름",
            "classified_at": db.utc_now(),
        },
    )

    context = news_pipeline.build_strategy_context(
        "interest_stock_radar_report",
        {"id": 1, "name": "관심종목 Radar", "schedule_type": "interest_stock_radar_report"},
        {"scope": "interest_stocks"},
        [{"ticker": "005930", "market": "KR", "name": "삼성전자"}],
        {"updated": [], "failed": []},
    )

    refined_news = context["pipeline"]["recent_refined_news"]
    assert refined_news
    assert refined_news[0]["title"] == "삼성전자 AI 반도체 기사 원문 제목"
    assert refined_news[0]["refined_summary"] == "HBM 수요 확대와 AI 반도체 모멘텀이 강화되는 흐름"
    assert refined_news[0]["has_raw_body"] is True
    assert context["strategy_view"]["items"][0]["summary"] == "HBM 수요 확대와 AI 반도체 모멘텀이 강화되는 흐름"
