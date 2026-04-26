import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .config import get_settings


JSON_FIELDS = {
    "tags",
    "alert_settings",
    "tickers",
    "target",
    "payload",
    "keywords",
    "linked_tickers",
    "raw_payload",
    "sectors",
    "user_links",
    "related_news_ids",
    "decision_json",
    "source_cluster_ids",
    "meta",
}
CREATED_AT_TABLES = {
    "interest_stock",
    "interest_area",
    "holding_stock",
    "expert_source",
    "schedule",
    "report",
    "notification_log",
    "news_raw",
    "news_refined",
    "news_cluster",
    "strategy_report",
    "pipeline_state",
}
UPDATED_AT_TABLES = {"interest_stock", "interest_area", "holding_stock", "expert_source", "schedule"}
LEGACY_DEFAULT_EXPERT_SOURCE_NAMES = {"FRED", "SEC EDGAR", "OpenDART", "Naver News Search"}
RETIRED_DEFAULT_NEWS_SOURCE_NAMES = {"Global markets", "Korea market", "US macro", "Semiconductor supply chain"}


def is_postgres() -> bool:
    return get_settings().database_url.startswith(("postgresql://", "postgres://"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> Path:
    return get_settings().sqlite_path


def connect():
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(get_settings().database_url, row_factory=dict_row)

    db_path = get_db_path()
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def db_session() -> Iterator[Any]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with db_session() as db:
        if is_postgres():
            _execute_script(
                db,
                """
                CREATE TABLE IF NOT EXISTS interest_stock (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                name TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                memo TEXT NOT NULL DEFAULT '',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                alert_settings TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS holding_stock (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                buy_date TEXT,
                target_price REAL,
                stop_loss_price REAL,
                memo TEXT NOT NULL DEFAULT '',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                alert_settings TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interest_area (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'research',
                keywords TEXT NOT NULL DEFAULT '[]',
                linked_tickers TEXT NOT NULL DEFAULT '[]',
                memo TEXT NOT NULL DEFAULT '',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS expert_source (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                trust_note TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schedule (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                tickers TEXT NOT NULL DEFAULT '[]',
                cron TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS codex_run (
                id SERIAL PRIMARY KEY,
                run_type TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '{}',
                agent_role TEXT NOT NULL DEFAULT '',
                prompt_path TEXT NOT NULL DEFAULT '',
                output_path TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS report (
                id SERIAL PRIMARY KEY,
                report_type TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '{}',
                title TEXT NOT NULL,
                markdown TEXT NOT NULL,
                codex_run_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_log (
                id SERIAL PRIMARY KEY,
                channel TEXT NOT NULL,
                target TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_snapshot (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL,
                captured_at TEXT NOT NULL
            );

                CREATE TABLE IF NOT EXISTS news_raw (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'news',
                published_at TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL,
                raw_summary TEXT NOT NULL DEFAULT '',
                raw_body TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL,
                raw_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS news_refined (
                id SERIAL PRIMARY KEY,
                news_raw_id INTEGER NOT NULL,
                tickers TEXT NOT NULL DEFAULT '[]',
                sectors TEXT NOT NULL DEFAULT '[]',
                importance INTEGER NOT NULL DEFAULT 1,
                sentiment TEXT NOT NULL DEFAULT 'neutral',
                user_links TEXT NOT NULL DEFAULT '{}',
                refined_summary TEXT NOT NULL DEFAULT '',
                classified_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS news_cluster (
                id SERIAL PRIMARY KEY,
                cluster_key TEXT NOT NULL,
                theme TEXT NOT NULL,
                narrative TEXT NOT NULL,
                related_news_ids TEXT NOT NULL DEFAULT '[]',
                tickers TEXT NOT NULL DEFAULT '[]',
                sectors TEXT NOT NULL DEFAULT '[]',
                importance_score REAL NOT NULL DEFAULT 1,
                cluster_window_start TEXT NOT NULL,
                cluster_window_end TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_report (
                id SERIAL PRIMARY KEY,
                report_type TEXT NOT NULL,
                schedule_id INTEGER,
                title TEXT NOT NULL,
                markdown TEXT NOT NULL,
                decision_json TEXT NOT NULL DEFAULT '{}',
                major_signal_detected BOOLEAN NOT NULL DEFAULT FALSE,
                notification_summary TEXT,
                source_cluster_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pipeline_state (
                id SERIAL PRIMARY KEY,
                pipeline_name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                last_cursor TEXT,
                last_started_at TEXT,
                last_finished_at TEXT,
                last_error TEXT,
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
            )
        else:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS interest_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    market TEXT NOT NULL,
                    name TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    memo TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    alert_settings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS holding_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    market TEXT NOT NULL,
                    name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    buy_date TEXT,
                    target_price REAL,
                    stop_loss_price REAL,
                    memo TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    alert_settings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS interest_area (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'research',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    linked_tickers TEXT NOT NULL DEFAULT '[]',
                    memo TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS expert_source (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    url TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    trust_note TEXT NOT NULL DEFAULT '',
                    last_checked_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    tickers TEXT NOT NULL DEFAULT '[]',
                    cron TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS codex_run (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '{}',
                    agent_role TEXT NOT NULL DEFAULT '',
                    prompt_path TEXT NOT NULL DEFAULT '',
                    output_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS report (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '{}',
                    title TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    codex_run_id INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL,
                    target TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    market TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL,
                    captured_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'news',
                    published_at TEXT NOT NULL DEFAULT '',
                    collected_at TEXT NOT NULL,
                    raw_summary TEXT NOT NULL DEFAULT '',
                    raw_body TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_refined (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_raw_id INTEGER NOT NULL,
                    tickers TEXT NOT NULL DEFAULT '[]',
                    sectors TEXT NOT NULL DEFAULT '[]',
                    importance INTEGER NOT NULL DEFAULT 1,
                    sentiment TEXT NOT NULL DEFAULT 'neutral',
                    user_links TEXT NOT NULL DEFAULT '{}',
                    refined_summary TEXT NOT NULL DEFAULT '',
                    classified_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_cluster (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_key TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    related_news_ids TEXT NOT NULL DEFAULT '[]',
                    tickers TEXT NOT NULL DEFAULT '[]',
                    sectors TEXT NOT NULL DEFAULT '[]',
                    importance_score REAL NOT NULL DEFAULT 1,
                    cluster_window_start TEXT NOT NULL,
                    cluster_window_end TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS strategy_report (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT NOT NULL,
                    schedule_id INTEGER,
                    title TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    decision_json TEXT NOT NULL DEFAULT '{}',
                    major_signal_detected INTEGER NOT NULL DEFAULT 0,
                    notification_summary TEXT,
                    source_cluster_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pipeline_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_name TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    last_cursor TEXT,
                    last_started_at TEXT,
                    last_finished_at TEXT,
                    last_error TEXT,
                    meta TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )
    ensure_runtime_columns()
    cleanup_legacy_schedules()
    cleanup_legacy_expert_sources()
    cleanup_retired_pipeline_rows()
    cleanup_unfetchable_query_news()
    seed_defaults()
    cleanup_seed_reports()


def _execute_script(db: Any, script: str) -> None:
    for statement in [part.strip() for part in script.split(";") if part.strip()]:
        db.execute(statement)


def ensure_runtime_columns() -> None:
    _ensure_column("news_raw", "raw_body", "TEXT NOT NULL DEFAULT ''")


def _ensure_column(table: str, column: str, definition: str) -> None:
    with db_session() as db:
        if is_postgres():
            db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
            return

        columns = {
            row["name"]
            for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in columns:
            return
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_defaults() -> None:
    for schedule in _default_schedules():
        _ensure_schedule(schedule)

    for source in _default_expert_sources():
        _sync_expert_source(source)

    if not list_rows("report"):
        insert(
            "report",
            {
                "report_type": "interest_area_radar",
                "target": {"scope": "seed"},
                "title": "초기 관심분야 Radar",
                "markdown": "\n".join(
                    [
                        "# 관심분야 Radar",
                        "",
                        "- 결론: seed 리포트입니다.",
                        "- 핵심 근거: 새 전략 파이프라인 화면 검증용 데이터입니다.",
                        "- 리스크: 실시간 데이터가 아닙니다.",
                        "- 다음 액션 기준: 뉴스 수집과 개인화 리포트가 실제 데이터로 누적되면 자동 대체됩니다.",
                    ]
                ),
                "codex_run_id": None,
                "created_at": utc_now(),
            },
        )

    if not list_rows("price_snapshot"):
        insert_price_snapshot("005930", "KR", 160500, None)
        insert_price_snapshot("TSLA", "US", 180, None)


def _default_expert_sources() -> List[Dict[str, Any]]:
    return [
        {
            "name": "BBC Business",
            "category": "business",
            "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 BBC Business RSS. 현재 환경에서 피드 접근과 본문 추출이 확인된 기본 경제 뉴스 소스.",
        },
        {
            "name": "BBC World",
            "category": "world_macro",
            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 BBC World RSS. 글로벌 지정학과 거시 이벤트 보강용 기본 소스.",
        },
        {
            "name": "The Guardian Business",
            "category": "business",
            "url": "https://www.theguardian.com/uk/business/rss",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 The Guardian Business RSS. 국제 경제와 기업 이슈 커버리지 보강용.",
        },
        {
            "name": "NPR Business",
            "category": "business",
            "url": "https://feeds.npr.org/1006/rss.xml",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 NPR Business RSS. 미국 경제/산업 뉴스 보강용.",
        },
        {
            "name": "ABC News Business",
            "category": "business",
            "url": "https://abcnews.go.com/abcnews/businessheadlines",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 ABC News Business RSS. 미국 기업/시장 뉴스 보강용.",
        },
        {
            "name": "Al Jazeera Global",
            "category": "world_macro",
            "url": "https://www.aljazeera.com/xml/rss/all.xml",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 Al Jazeera RSS. 지정학, 원자재, 글로벌 매크로 뉴스 보강용.",
        },
        {
            "name": "Fortune",
            "category": "business",
            "url": "https://fortune.com/feed/",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 Fortune RSS. 글로벌 비즈니스와 기업 전략 뉴스 보강용.",
        },
        {
            "name": "Forbes Business",
            "category": "business",
            "url": "https://www.forbes.com/business/feed/",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 Forbes Business RSS. 비즈니스/시장 기사 보강용.",
        },
        {
            "name": "Federal Reserve Press Releases",
            "category": "central_bank",
            "url": "https://www.federalreserve.gov/feeds/press_all.xml",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 연준 보도자료 RSS. 금리/유동성/정책 이벤트의 1차 소스.",
        },
        {
            "name": "ECB Press Releases",
            "category": "central_bank",
            "url": "https://www.ecb.europa.eu/rss/press.html",
            "platform": "rss",
            "enabled": True,
            "trust_note": "공식 ECB 보도자료 RSS. 유럽 거시정책 이벤트의 1차 소스.",
        },
        {
            "name": "오건영 Facebook",
            "category": "macro",
            "url": "https://www.facebook.com/ohrang79",
            "platform": "facebook",
            "enabled": False,
            "trust_note": "오건영님 Facebook으로 널리 인용되는 URL. 사칭 방지를 위해 사용자가 확인 후 활성화한다.",
        },
    ]


def _default_schedules() -> List[Dict[str, Any]]:
    return [
        {
            "name": "09:00 관심분야 연구성과 감지",
            "schedule_type": "interest_area_research_watch",
            "target_type": "areas",
            "tickers": [],
            "cron": "매일 09:00 KST",
            "enabled": True,
        },
        {
            "name": "5분 급변 알림",
            "schedule_type": "price_alert_watch",
            "target_type": "all",
            "tickers": [],
            "cron": "장중 5분마다",
            "enabled": True,
        },
        {
            "name": "수동 Codex 분석",
            "schedule_type": "manual_codex_analysis",
            "target_type": "tickers",
            "tickers": [],
            "cron": "버튼 또는 자연어 명령으로 실행",
            "enabled": True,
        },
        {
            "name": "07:30 관심분야 Radar",
            "schedule_type": "interest_area_radar_report",
            "target_type": "areas",
            "tickers": [],
            "cron": "매일 07:30 KST",
            "enabled": True,
        },
        {
            "name": "08:40 관심종목 Radar",
            "schedule_type": "interest_stock_radar_report",
            "target_type": "interest",
            "tickers": [],
            "cron": "매일 08:40 KST",
            "enabled": True,
        },
    ]


def _ensure_schedule(schedule: Dict[str, Any]) -> None:
    for row in list_rows("schedule"):
        if row.get("name") == schedule["name"]:
            return
    insert("schedule", schedule)


def _ensure_expert_source(source: Dict[str, Any]) -> None:
    for row in list_rows("expert_source"):
        if row.get("url") == source["url"] or row.get("name") == source["name"]:
            return
    insert("expert_source", {**source, "last_checked_at": None})


def _sync_expert_source(source: Dict[str, Any]) -> None:
    for row in list_rows("expert_source"):
        if row.get("url") == source["url"] or row.get("name") == source["name"]:
            update_values = {
                "name": source["name"],
                "category": source["category"],
                "url": source["url"],
                "platform": source["platform"],
                "trust_note": source["trust_note"],
            }
            if row.get("enabled") is None:
                update_values["enabled"] = source["enabled"]
            update_row("expert_source", row["id"], update_values)
            return
    insert("expert_source", {**source, "last_checked_at": None})


def cleanup_legacy_expert_sources() -> None:
    for row in list_rows("expert_source"):
        if row.get("name") in LEGACY_DEFAULT_EXPERT_SOURCE_NAMES:
            delete_row("expert_source", row["id"])


def cleanup_retired_pipeline_rows() -> None:
    retired_raw_ids = {
        row["id"]
        for row in list_rows("news_raw")
        if row.get("source") in RETIRED_DEFAULT_NEWS_SOURCE_NAMES
    }
    if not retired_raw_ids:
        return

    for row in list_rows("news_refined"):
        if row.get("news_raw_id") in retired_raw_ids:
            delete_row("news_refined", row["id"])

    for row in list_rows("news_cluster"):
        related_ids = set(row.get("related_news_ids") or [])
        if related_ids & retired_raw_ids:
            delete_row("news_cluster", row["id"])

    for raw_id in retired_raw_ids:
        delete_row("news_raw", raw_id)


def cleanup_unfetchable_query_news() -> None:
    dropped_raw_ids = set()
    for row in list_rows("news_raw"):
        if (row.get("raw_body") or "").strip():
            continue
        if row.get("category") not in {"stock_watch", "interest_area"}:
            continue
        payload = row.get("raw_payload") or {}
        attempts = int(payload.get("article_fetch_attempts") or 0)
        last_error = str(payload.get("article_fetch_last_error") or "")
        if attempts >= 3 and "403" in last_error:
            dropped_raw_ids.add(row["id"])

    if not dropped_raw_ids:
        return

    for row in list_rows("news_refined"):
        if row.get("news_raw_id") in dropped_raw_ids:
            delete_row("news_refined", row["id"])

    for row in list_rows("news_cluster"):
        related_ids = set(row.get("related_news_ids") or [])
        if related_ids & dropped_raw_ids:
            delete_row("news_cluster", row["id"])

    for raw_id in dropped_raw_ids:
        delete_row("news_raw", raw_id)


def encode_value(key: str, value: Any) -> Any:
    if key in JSON_FIELDS:
        return json.dumps(
            value
            if value is not None
            else ([] if key in {"tags", "tickers", "keywords", "linked_tickers", "sectors", "related_news_ids", "source_cluster_ids"} else {}),
            ensure_ascii=False,
        )
    if isinstance(value, bool):
        return value if is_postgres() else (1 if value else 0)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__str__") and value.__class__.__name__ in {"Url", "HttpUrl"}:
        return str(value)
    return value


def decode_row(row: Any) -> Dict[str, Any]:
    item = dict(row)
    for key in list(item.keys()):
        if key in JSON_FIELDS and isinstance(item[key], str):
            item[key] = json.loads(item[key] or "{}")
        if key == "enabled" and item[key] is not None:
            item[key] = bool(item[key])
    return item


def insert(table: str, values: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now()
    values = dict(values)
    if table in CREATED_AT_TABLES and "created_at" not in values:
        values["created_at"] = now
    if table in UPDATED_AT_TABLES and "updated_at" not in values:
        values["updated_at"] = now
    keys = list(values.keys())
    placeholders = ", ".join(_placeholder() for _ in keys)
    columns = ", ".join(keys)
    encoded = [encode_value(key, values[key]) for key in keys]
    with db_session() as db:
        if is_postgres():
            row = db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *", encoded).fetchone()
        else:
            cursor = db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", encoded)
            row_id = cursor.lastrowid
            row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return decode_row(row)


def list_rows(table: str) -> List[Dict[str, Any]]:
    with db_session() as db:
        rows = db.execute(f"SELECT * FROM {table} ORDER BY id DESC").fetchall()
    return [decode_row(row) for row in rows]


def insert_price_snapshot(ticker: str, market: str, price: float, volume: Optional[float]) -> Dict[str, Any]:
    return insert(
        "price_snapshot",
        {
            "ticker": ticker,
            "market": market,
            "price": price,
            "volume": volume,
            "captured_at": utc_now(),
        },
    )


def latest_price(ticker: str, market: str) -> Optional[float]:
    with db_session() as db:
        row = db.execute(
            f"""
            SELECT price FROM price_snapshot
            WHERE ticker = {_placeholder()} AND market = {_placeholder()}
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            _params(ticker, market),
        ).fetchone()
    return float(row["price"]) if row else None


def get_row(table: str, row_id: int) -> Optional[Dict[str, Any]]:
    with db_session() as db:
        row = db.execute(f"SELECT * FROM {table} WHERE id = {_placeholder()}", _params(row_id)).fetchone()
    return decode_row(row) if row else None


def update_row(table: str, row_id: int, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    values = {key: value for key, value in values.items() if value is not None}
    if table in UPDATED_AT_TABLES:
        values["updated_at"] = utc_now()
    if not values:
        return get_row(table, row_id)
    assignments = ", ".join(f"{key} = {_placeholder()}" for key in values.keys())
    encoded = [encode_value(key, values[key]) for key in values.keys()]
    with db_session() as db:
        if is_postgres():
            row = db.execute(f"UPDATE {table} SET {assignments} WHERE id = {_placeholder()} RETURNING *", [*encoded, row_id]).fetchone()
        else:
            db.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", [*encoded, row_id])
            row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return decode_row(row) if row else None


def delete_row(table: str, row_id: int) -> bool:
    with db_session() as db:
        cursor = db.execute(f"DELETE FROM {table} WHERE id = {_placeholder()}", _params(row_id))
    return cursor.rowcount > 0


def delete_older_than(table: str, column: str, cutoff_iso: str) -> int:
    with db_session() as db:
        cursor = db.execute(
            f"DELETE FROM {table} WHERE {column} < {_placeholder()}",
            _params(cutoff_iso),
        )
    return cursor.rowcount


def delete_all_rows(table: str) -> int:
    with db_session() as db:
        cursor = db.execute(f"DELETE FROM {table}")
    return cursor.rowcount


def cleanup_seed_reports() -> None:
    for row in list_rows("report"):
        target = row.get("target") or {}
        if target.get("scope") == "seed":
            delete_row("report", row["id"])


def cleanup_legacy_schedules() -> None:
    legacy_types = {"global_news_digest", "stock_report", "holding_decision_report"}
    for row in list_rows("schedule"):
        if row.get("schedule_type") in legacy_types:
            delete_row("schedule", row["id"])


def get_pipeline_state(pipeline_name: str) -> Optional[Dict[str, Any]]:
    with db_session() as db:
        row = db.execute(
            f"SELECT * FROM pipeline_state WHERE pipeline_name = {_placeholder()}",
            _params(pipeline_name),
        ).fetchone()
    return decode_row(row) if row else None


def upsert_pipeline_state(pipeline_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
    existing = get_pipeline_state(pipeline_name)
    payload = dict(values)
    payload["pipeline_name"] = pipeline_name
    if existing is None:
        return insert("pipeline_state", payload)
    return update_row("pipeline_state", existing["id"], payload) or existing


def _placeholder() -> str:
    return "%s" if is_postgres() else "?"


def _params(*values: Any) -> tuple:
    return tuple(values)
