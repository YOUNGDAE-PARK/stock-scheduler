from contextlib import asynccontextmanager
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Type

from fastapi import FastAPI, HTTPException, Query
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
from .services.notifications import send_test_notification
from .services.schedule_runner import run_schedule_now


TABLES = {
    "interests": "interest_stock",
    "interest-areas": "interest_area",
    "holdings": "holding_stock",
    "expert-sources": "expert_source",
    "schedules": "schedule",
}


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
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|10\.0\.0\.2|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+):5173",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/diagnostics/codex")
def codex_diagnostics() -> Dict[str, Any]:
    settings = get_settings()
    codex_bin = settings.codex_bin
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    auth_path = codex_home / "auth.json"
    config_path = codex_home / "config.toml"
    return {
        "codex_bin": codex_bin,
        "codex_bin_resolved": shutil.which(codex_bin) or shutil.which("codex"),
        "codex_bin_exists": Path(codex_bin).exists() or shutil.which(codex_bin) is not None,
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
        return run_schedule_now(row_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


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
