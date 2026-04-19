from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


Market = Literal["KR", "US"]
ScheduleType = Literal[
    "stock_report",
    "price_alert_watch",
    "global_news_digest",
    "manual_codex_analysis",
    "interest_area_research_watch",
]
ScheduleTarget = Literal["interest", "holding", "all", "tickers", "areas"]


class InterestCreate(BaseModel):
    ticker: str
    market: Market
    name: str
    tags: List[str] = Field(default_factory=list)
    memo: str = ""
    enabled: bool = True
    alert_settings: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("ticker is required")
        return value


class InterestUpdate(BaseModel):
    ticker: Optional[str] = None
    market: Optional[Market] = None
    name: Optional[str] = None
    tags: Optional[List[str]] = None
    memo: Optional[str] = None
    enabled: Optional[bool] = None
    alert_settings: Optional[Dict[str, Any]] = None


class Interest(InterestCreate):
    id: int
    current_price: Optional[float] = None
    created_at: str
    updated_at: str


class InterestAreaCreate(BaseModel):
    name: str
    category: str = "research"
    keywords: List[str] = Field(default_factory=list)
    linked_tickers: List[str] = Field(default_factory=list)
    memo: str = ""
    enabled: bool = True

    @field_validator("name", "category")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value is required")
        return value


class InterestAreaUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[List[str]] = None
    linked_tickers: Optional[List[str]] = None
    memo: Optional[str] = None
    enabled: Optional[bool] = None


class InterestArea(InterestAreaCreate):
    id: int
    created_at: str
    updated_at: str


class HoldingCreate(BaseModel):
    ticker: str
    market: Market
    name: str
    quantity: float = Field(gt=0)
    avg_price: float = Field(gt=0)
    buy_date: Optional[date] = None
    target_price: Optional[float] = Field(default=None, gt=0)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    memo: str = ""
    enabled: bool = True
    alert_settings: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("ticker is required")
        return value


class HoldingUpdate(BaseModel):
    ticker: Optional[str] = None
    market: Optional[Market] = None
    name: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    avg_price: Optional[float] = Field(default=None, gt=0)
    buy_date: Optional[date] = None
    target_price: Optional[float] = Field(default=None, gt=0)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    memo: Optional[str] = None
    enabled: Optional[bool] = None
    alert_settings: Optional[Dict[str, Any]] = None


class Holding(HoldingCreate):
    id: int
    current_price: Optional[float] = None
    created_at: str
    updated_at: str


class ExpertSourceCreate(BaseModel):
    name: str
    category: str = "macro"
    url: HttpUrl
    platform: str
    enabled: bool = False
    trust_note: str = ""
    last_checked_at: Optional[str] = None


class ExpertSourceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    url: Optional[HttpUrl] = None
    platform: Optional[str] = None
    enabled: Optional[bool] = None
    trust_note: Optional[str] = None
    last_checked_at: Optional[str] = None


class ExpertSource(BaseModel):
    id: int
    name: str
    category: str
    url: str
    platform: str
    enabled: bool
    trust_note: str
    last_checked_at: Optional[str] = None
    created_at: str
    updated_at: str


class ScheduleCreate(BaseModel):
    name: str
    schedule_type: ScheduleType
    target_type: ScheduleTarget
    tickers: List[str] = Field(default_factory=list)
    cron: str
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    schedule_type: Optional[ScheduleType] = None
    target_type: Optional[ScheduleTarget] = None
    tickers: Optional[List[str]] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None


class Schedule(ScheduleCreate):
    id: int
    created_at: str
    updated_at: str


class CommandRequest(BaseModel):
    text: str
    execute: bool = True


class CommandResponse(BaseModel):
    status: Literal["executed", "needs_confirmation", "unsupported"]
    intent: str
    message: str
    result: Optional[Dict[str, Any]] = None


class AnalysisRunRequest(BaseModel):
    run_type: ScheduleType = "manual_codex_analysis"
    target: Dict[str, Any] = Field(default_factory=dict)
    agent_role: str = "final-investment-opinion"


class AnalysisRun(BaseModel):
    id: int
    run_type: str
    target: Dict[str, Any]
    agent_role: str
    prompt_path: str
    output_path: str
    status: str
    started_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None


class Report(BaseModel):
    id: int
    report_type: str
    target: Dict[str, Any]
    title: str
    markdown: str
    codex_run_id: Optional[int] = None
    created_at: str


class NotificationTestRequest(BaseModel):
    target: str = "galaxy-s24"
    title: str = "stock_scheduler 테스트 알림"
    body: str = "Telegram 알림이 정상 연결되었습니다."
    payload: Dict[str, Any] = Field(default_factory=dict)


class NotificationLog(BaseModel):
    id: int
    channel: str
    target: str
    title: str
    body: str
    payload: Dict[str, Any]
    status: str
    error: Optional[str] = None
    created_at: str
