from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Type

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .command_parser import parse_and_execute
from .config import get_settings
from .scheduler import create_scheduler
from .schemas import (
    AnalysisRun,
    AnalysisRunRequest,
    CommandRequest,
    CommandResponse,
    ExpertSource,
    ExpertSourceCreate,
    ExpertSourceUpdate,
    Holding,
    HoldingCreate,
    HoldingUpdate,
    Interest,
    InterestArea,
    InterestAreaCreate,
    InterestAreaUpdate,
    InterestCreate,
    InterestUpdate,
    NotificationLog,
    NotificationTestRequest,
    Report,
    Schedule,
    ScheduleCreate,
    ScheduleUpdate,
)
from .services.codex_runner import run_dry_analysis
from .services.kis import KisApiError, get_kis_client
from .services.news_pipeline import run_news_pipeline_chain
from .services.notifications import send_test_notification
from .services.schedule_runner import run_schedule_now

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


TABLES = {
    "interests": "interest_stock",
    "interest-areas": "interest_area",
    "holdings": "holding_stock",
    "expert-sources": "expert_source",
    "schedules": "schedule",
}
LOCAL_CORS_ORIGIN_PATTERN = re.compile(
    r"http://(localhost|127\.0\.0\.1|10\.0\.0\.2|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+):5173"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="stock_scheduler", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()],
    allow_origin_regex=LOCAL_CORS_ORIGIN_PATTERN.pattern,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/api/{path:path}")
def api_preflight(path: str, request: Request) -> Response:
    origin = request.headers.get("origin", "")
    allowed = {item.strip() for item in settings.cors_allow_origins.split(",") if item.strip()}
    headers = {
        "Access-Control-Allow-Methods": "DELETE,GET,OPTIONS,PATCH,POST,PUT",
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "*"),
        "Access-Control-Allow-Credentials": "true",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    return Response(status_code=204, headers=headers)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/diagnostics/codex")
def codex_diagnostics() -> Dict[str, Any]:
    settings = get_settings()
    codex_bin = settings.codex_bin
    codex_resolved = shutil.which(codex_bin) or shutil.which("codex")
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    auth_path = codex_home / "auth.json"
    config_path = codex_home / "config.toml"
    return {
        "codex_bin": codex_bin,
        "codex_bin_resolved": codex_resolved,
        "codex_bin_exists": Path(codex_bin).exists() or codex_resolved is not None,
        "codex_home": str(codex_home),
        "auth_json_exists": auth_path.exists(),
        "config_toml_exists": config_path.exists(),
    }


def _create(table: str, payload: BaseModel) -> Dict[str, Any]:
    return _with_current_price(table, db.insert(table, payload.model_dump(exclude_none=False)))


def _list(table: str) -> List[Dict[str, Any]]:
    return [_with_current_price(table, row) for row in db.list_rows(table)]


def _patch(table: str, row_id: int, payload: BaseModel) -> Dict[str, Any]:
    row = db.update_row(table, row_id, payload.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return _with_current_price(table, row)


def _delete(table: str, row_id: int) -> Dict[str, bool]:
    if not db.delete_row(table, row_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}


def _with_current_price(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    if table not in {"interest_stock", "holding_stock"}:
        return row
    enriched = dict(row)
    enriched["current_price"] = db.latest_price(row["ticker"], row["market"])
    return enriched


def _upsert_stock(table: str, payload: BaseModel) -> Dict[str, Any]:
    values = payload.model_dump(exclude_none=False)
    for row in db.list_rows(table):
        if row.get("ticker") == values.get("ticker") and row.get("market") == values.get("market"):
            updated = db.update_row(table, row["id"], values)
            return _with_current_price(table, updated)
    return _with_current_price(table, db.insert(table, values))


@app.post("/api/interests", response_model=Interest)
def create_interest(payload: InterestCreate):
    return _upsert_stock(TABLES["interests"], payload)


@app.get("/api/interests", response_model=List[Interest])
def list_interests():
    return _list(TABLES["interests"])


@app.patch("/api/interests/{row_id}", response_model=Interest)
def update_interest(row_id: int, payload: InterestUpdate):
    return _patch(TABLES["interests"], row_id, payload)


@app.delete("/api/interests/{row_id}")
def delete_interest(row_id: int):
    return _delete(TABLES["interests"], row_id)


@app.post("/api/interest-areas", response_model=InterestArea)
def create_interest_area(payload: InterestAreaCreate):
    return _create(TABLES["interest-areas"], payload)


@app.get("/api/interest-areas", response_model=List[InterestArea])
def list_interest_areas():
    return _list(TABLES["interest-areas"])


@app.patch("/api/interest-areas/{row_id}", response_model=InterestArea)
def update_interest_area(row_id: int, payload: InterestAreaUpdate):
    return _patch(TABLES["interest-areas"], row_id, payload)


@app.delete("/api/interest-areas/{row_id}")
def delete_interest_area(row_id: int):
    return _delete(TABLES["interest-areas"], row_id)


@app.post("/api/holdings", response_model=Holding)
def create_holding(payload: HoldingCreate):
    return _upsert_stock(TABLES["holdings"], payload)


@app.get("/api/holdings", response_model=List[Holding])
def list_holdings():
    return _list(TABLES["holdings"])


@app.patch("/api/holdings/{row_id}", response_model=Holding)
def update_holding(row_id: int, payload: HoldingUpdate):
    return _patch(TABLES["holdings"], row_id, payload)


@app.delete("/api/holdings/{row_id}")
def delete_holding(row_id: int):
    return _delete(TABLES["holdings"], row_id)


@app.post("/api/schedules", response_model=Schedule)
def create_schedule(payload: ScheduleCreate):
    return _create(TABLES["schedules"], payload)


@app.get("/api/schedules", response_model=List[Schedule])
def list_schedules():
    return _list(TABLES["schedules"])


@app.patch("/api/schedules/{row_id}", response_model=Schedule)
def update_schedule(row_id: int, payload: ScheduleUpdate):
    return _patch(TABLES["schedules"], row_id, payload)


@app.delete("/api/schedules/{row_id}")
def delete_schedule(row_id: int):
    return _delete(TABLES["schedules"], row_id)


@app.post("/api/schedules/{row_id}/run")
def run_schedule(row_id: int) -> Dict[str, Any]:
    try:
        logger.info("api schedule run request row_id=%s", row_id)
        return run_schedule_now(row_id)
    except ValueError as exc:
        message = str(exc)
        logger.warning("api schedule run value error row_id=%s error=%s", row_id, message)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
    except Exception as exc:
        logger.exception("api schedule run unexpected error row_id=%s", row_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/expert-sources", response_model=ExpertSource)
def create_expert_source(payload: ExpertSourceCreate):
    return _create(TABLES["expert-sources"], payload)


@app.get("/api/expert-sources", response_model=List[ExpertSource])
def list_expert_sources():
    return _list(TABLES["expert-sources"])


@app.patch("/api/expert-sources/{row_id}", response_model=ExpertSource)
def update_expert_source(row_id: int, payload: ExpertSourceUpdate):
    return _patch(TABLES["expert-sources"], row_id, payload)


@app.delete("/api/expert-sources/{row_id}")
def delete_expert_source(row_id: int):
    return _delete(TABLES["expert-sources"], row_id)


@app.post("/api/commands", response_model=CommandResponse)
def run_command(payload: CommandRequest):
    return parse_and_execute(payload.text, payload.execute)


@app.post("/api/analysis/run", response_model=AnalysisRun)
def run_analysis(payload: AnalysisRunRequest):
    # 실제 provider 연결이 완료되었으므로 dry-run을 실제 분석으로 교체
    # manual_codex_analysis는 target stocks 정보를 context로 넘겨야 함
    ticker = payload.target.get("ticker", "UNKNOWN")
    market = payload.target.get("market", "KR")
    name = payload.target.get("name") or ticker
    stocks = [{"ticker": ticker, "market": market, "name": name}]
    context = {
        "schedule": {"name": "수동 분석", "schedule_type": payload.run_type},
        "target": payload.target,
        "stocks": stocks,
        "prices": {"updated": stocks, "failed": []},
        "enabled_sources": [source for source in db.list_rows("expert_source") if source.get("enabled")],
        "global_news": {"items": [], "sources": [], "errors": []},
    }
    try:
        from .services.codex_runner import run_codex_schedule_analysis
        result = run_codex_schedule_analysis(payload.run_type, payload.target, context)
    except Exception:
        # 실패 시 기존처럼 dry-run 또는 fallback 리포트 생성
        result = run_dry_analysis(payload.run_type, payload.target, payload.agent_role)
    return result["run"]


@app.get("/api/analysis/runs/{row_id}", response_model=AnalysisRun)
def get_analysis_run(row_id: int):
    row = db.get_row("codex_run", row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.get("/api/reports", response_model=List[Report])
def list_reports():
    return db.list_rows("report")


@app.get("/api/reports/{row_id}", response_model=Report)
def get_report(row_id: int):
    row = db.get_row("report", row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.post("/api/reports/clear")
def clear_reports() -> Dict[str, int]:
    deleted_reports = db.delete_all_rows("report")
    deleted_strategy_reports = db.delete_all_rows("strategy_report")
    return {
        "deleted_reports": deleted_reports,
        "deleted_strategy_reports": deleted_strategy_reports,
    }


@app.post("/api/pipeline/backfill")
def run_pipeline_backfill() -> Dict[str, Any]:
    try:
        return run_news_pipeline_chain(force_collect=True)
    except Exception as exc:
        logger.exception("pipeline backfill failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/e2e/run")
def run_e2e_flow(schedule_type: str = Query("interest_area_radar_report")) -> Dict[str, Any]:
    try:
        pipeline = run_news_pipeline_chain(force_collect=True)
        schedule = next(
            (row for row in db.list_rows("schedule") if row.get("schedule_type") == schedule_type and row.get("enabled")),
            None,
        )
        if schedule is None:
            raise HTTPException(status_code=404, detail=f"enabled schedule not found: {schedule_type}")
        result = run_schedule_now(schedule["id"])
        return {
            "status": "completed",
            "pipeline": pipeline,
            "schedule": schedule,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("e2e flow failed schedule_type=%s", schedule_type)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/pipeline/news-raw")
def list_news_raw(limit: int = Query(100, ge=1, le=500)) -> List[Dict[str, Any]]:
    return db.list_rows("news_raw")[:limit]


@app.get("/api/pipeline/news-refined")
def list_news_refined(limit: int = Query(100, ge=1, le=500)) -> List[Dict[str, Any]]:
    return db.list_rows("news_refined")[:limit]


@app.get("/api/pipeline/news-cluster")
def list_news_cluster(limit: int = Query(100, ge=1, le=500)) -> List[Dict[str, Any]]:
    return db.list_rows("news_cluster")[:limit]


@app.get("/api/pipeline/strategy-reports")
def list_strategy_reports(limit: int = Query(100, ge=1, le=500)) -> List[Dict[str, Any]]:
    return db.list_rows("strategy_report")[:limit]


@app.get("/api/pipeline/state")
def list_pipeline_state() -> List[Dict[str, Any]]:
    return db.list_rows("pipeline_state")


@app.post("/api/notifications/test", response_model=NotificationLog)
def test_notification(payload: NotificationTestRequest):
    return send_test_notification(payload.target, payload.title, payload.body, payload.payload)


@app.get("/api/providers/kis/domestic-price/{ticker}")
def get_kis_domestic_price(ticker: str) -> Dict[str, Any]:
    try:
        return get_kis_client().inquire_domestic_price(ticker)
    except KisApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/providers/kis/domestic-prices")
def get_kis_domestic_prices(
    tickers: str = Query(..., description="Comma separated domestic stock tickers. Max 30 per KIS request."),
    market: str = Query("J", description="KIS market division code. J=KRX, NX=NXT."),
) -> Dict[str, Any]:
    ticker_list = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
    if not ticker_list:
        raise HTTPException(status_code=422, detail="tickers must contain at least one ticker")
    try:
        return get_kis_client().inquire_domestic_prices(ticker_list, market)
    except KisApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
