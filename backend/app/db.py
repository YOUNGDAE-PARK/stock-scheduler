import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .config import get_settings


JSON_FIELDS = {"tags", "alert_settings", "tickers", "target", "payload", "keywords", "linked_tickers"}
CREATED_AT_TABLES = {
    "interest_stock",
    "interest_area",
    "holding_stock",
    "expert_source",
    "schedule",
    "report",
    "notification_log",
}
UPDATED_AT_TABLES = {"interest_stock", "interest_area", "holding_stock", "expert_source", "schedule"}


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
                """
            )
    seed_defaults()


def _execute_script(db: Any, script: str) -> None:
    for statement in [part.strip() for part in script.split(";") if part.strip()]:
        db.execute(statement)


def seed_defaults() -> None:
    for schedule in _default_schedules():
        _ensure_schedule(schedule)

    if not list_rows("expert_source"):
        for source in _default_expert_sources():
            insert("expert_source", {**source, "last_checked_at": None})
    else:
        _ensure_expert_source(
            {
                "name": "오건영 Facebook",
                "category": "macro",
                "url": "https://www.facebook.com/ohrang79",
                "platform": "facebook",
                "enabled": False,
                "trust_note": "오건영님 Facebook으로 널리 인용되는 URL. 사칭 방지를 위해 사용자가 확인 후 활성화한다.",
            }
        )

    if not list_rows("report"):
        insert(
            "report",
            {
                "report_type": "global_news_digest",
                "target": {"scope": "seed"},
                "title": "초기 글로벌 경제뉴스 요약",
                "markdown": "\n".join(
                    [
                        "# 글로벌 경제뉴스 요약",
                        "",
                        "- 결론: seed 리포트입니다.",
                        "- 핵심 근거: 실제 뉴스 provider 연결 전 화면 검증용 데이터입니다.",
                        "- 리스크: 실시간 데이터가 아닙니다.",
                        "- 다음 액션 기준: FRED, SEC EDGAR, OpenDART, Naver News Search provider 연결.",
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
            "name": "FRED",
            "category": "macro",
            "url": "https://fred.stlouisfed.org/docs/api/fred/",
            "platform": "api",
            "enabled": True,
            "trust_note": "거시경제 데이터 API",
        },
        {
            "name": "SEC EDGAR",
            "category": "disclosure",
            "url": "https://www.sec.gov/about/developer-resources",
            "platform": "api",
            "enabled": True,
            "trust_note": "미국 공시 데이터",
        },
        {
            "name": "OpenDART",
            "category": "disclosure",
            "url": "https://opendart.fss.or.kr/",
            "platform": "api",
            "enabled": True,
            "trust_note": "한국 공시 데이터",
        },
        {
            "name": "Naver News Search",
            "category": "news",
            "url": "https://developers.naver.com/docs/serviceapi/search/news/news.md",
            "platform": "api",
            "enabled": True,
            "trust_note": "한국 뉴스 검색",
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
            "name": "08:00 글로벌 경제뉴스",
            "schedule_type": "global_news_digest",
            "target_type": "all",
            "tickers": [],
            "cron": "매일 08:00 KST",
            "enabled": True,
        },
        {
            "name": "09:00 관심분야 연구성과 감지",
            "schedule_type": "interest_area_research_watch",
            "target_type": "areas",
            "tickers": [],
            "cron": "매일 09:00 KST",
            "enabled": True,
        },
        {
            "name": "18:00 글로벌 경제뉴스",
            "schedule_type": "global_news_digest",
            "target_type": "all",
            "tickers": [],
            "cron": "매일 18:00 KST",
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


def encode_value(key: str, value: Any) -> Any:
    if key in JSON_FIELDS:
        return json.dumps(
            value if value is not None else ([] if key in {"tags", "tickers", "keywords", "linked_tickers"} else {}),
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


def _placeholder() -> str:
    return "%s" if is_postgres() else "?"


def _params(*values: Any) -> tuple:
    return tuple(values)
