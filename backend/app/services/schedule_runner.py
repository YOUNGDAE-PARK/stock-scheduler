from typing import Any, Dict, List, Optional

from .. import db
from .codex_runner import OrchestratorAnalysisError, run_codex_schedule_analysis
from .kis import KisApiError, get_kis_client
from .news import collect_global_news
from .notifications import send_notification


REPORT_SCHEDULE_TYPES = {"stock_report", "manual_codex_analysis", "global_news_digest", "interest_area_research_watch"}


def run_schedule_now(schedule_id: int) -> Dict[str, Any]:
    schedule = db.get_row("schedule", schedule_id)
    if schedule is None:
        raise ValueError("schedule not found")

    schedule_type = schedule["schedule_type"]
    target = _schedule_target(schedule)
    stocks = _target_stocks(schedule)
    price_result = _refresh_prices_for_schedule(schedule_type, stocks)

    if schedule_type == "price_alert_watch":
        notification = _send_price_watch_notification(schedule, target, price_result)
        return {
            "status": "completed",
            "schedule": schedule,
            "prices": price_result,
            "notification": notification,
            "message": f"{schedule['name']} 실행 완료: 현재가를 조회하고 알림을 보냈습니다.",
        }

    if schedule_type in REPORT_SCHEDULE_TYPES:
        result = _create_schedule_report(schedule, target, stocks, price_result)
        notification = None
        if _should_notify_report(schedule, result):
            notification = _send_report_notification(schedule, target, result["report"], result["run"])
        return {
            "status": "completed",
            "schedule": schedule,
            "prices": price_result,
            "run": result["run"],
            "report": result["report"],
            "notification": notification,
            "message": f"{schedule['name']} 실행 완료: 실제 데이터 기반 리포트를 생성했습니다.",
        }

    raise ValueError(f"unsupported schedule type: {schedule_type}")


def _send_price_watch_notification(
    schedule: Dict[str, Any],
    target: Dict[str, Any],
    price_result: Dict[str, Any],
) -> Dict[str, Any]:
    updated = price_result["updated"]
    failed = price_result["failed"]
    lines = [f"조회 성공 {len(updated)}건, 실패 {len(failed)}건"]
    for item in updated[:10]:
        lines.append(f"{item['name']}({item['ticker']}): {item['price']}")
    if failed:
        lines.append("실패: " + ", ".join(item["ticker"] for item in failed[:10]))

    return send_notification(
        "galaxy-s24",
        f"{schedule['name']} 실행 결과",
        "\n".join(lines),
        {"source": "schedule", "schedule_id": schedule["id"], "schedule_type": schedule["schedule_type"], "target": target},
    )


def _send_report_notification(
    schedule: Dict[str, Any],
    target: Dict[str, Any],
    report: Dict[str, Any],
    run: Dict[str, Any],
) -> Dict[str, Any]:
    from ..config import get_settings
    orch_label = get_settings().orchestrator_type.capitalize()
    status_label = f"{orch_label} 분석 완료" if run.get("status") == "completed" else f"{orch_label} 분석 실패, fallback 리포트 생성"
    body = "\n".join(
        [
            status_label,
            f"리포트: {report['title']}",
            f"리포트 ID: {report['id']}",
        ]
    )
    return send_notification(
        "galaxy-s24",
        f"{schedule['name']} 리포트 생성",
        body,
        {
            "source": "schedule_report",
            "schedule_id": schedule["id"],
            "schedule_type": schedule["schedule_type"],
            "report_id": report["id"],
            "report_markdown": report.get("markdown", ""),
            "run_status": run.get("status"),
            "target": target,
        },
    )


def _create_schedule_report(
    schedule: Dict[str, Any],
    target: Dict[str, Any],
    stocks: List[Dict[str, Any]],
    price_result: Dict[str, Any],
) -> Dict[str, Any]:
    enabled_sources = [source for source in db.list_rows("expert_source") if source.get("enabled")]
    interest_areas = [area for area in db.list_rows("interest_area") if area.get("enabled")]
    global_news = _collect_news_for_schedule(schedule, enabled_sources, stocks, interest_areas)
    context = {
        "schedule": schedule,
        "target": target,
        "stocks": stocks,
        "interest_areas": interest_areas,
        "prices": price_result,
        "enabled_sources": enabled_sources,
        "global_news": global_news,
        "provider_notes": {
            "kis": "Connected for KR domestic current prices.",
            "telegram": "Connected when NOTIFICATION_MODE=telegram.",
            "news_disclosure_social": "RSS/search headline collection is connected for global_news_digest. Full article body, paid APIs, Facebook scraping, FRED observations, and disclosure parsers are not connected yet.",
        },
    }
    try:
        return run_codex_schedule_analysis(schedule["schedule_type"], target, context)
    except OrchestratorAnalysisError as exc:
        return _create_fallback_report(schedule, target, stocks, price_result, str(exc), global_news)


def _create_fallback_report(
    schedule: Dict[str, Any],
    target: Dict[str, Any],
    stocks: List[Dict[str, Any]],
    price_result: Dict[str, Any],
    error: str,
    global_news: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    started = db.utc_now()
    run = db.insert(
        "codex_run",
        {
            "run_type": schedule["schedule_type"],
            "target": target,
            "agent_role": "schedule-analysis",
            "prompt_path": "fallback",
            "output_path": "",
            "status": "failed_fallback_report_created",
            "started_at": started,
            "finished_at": db.utc_now(),
            "error": error,
        },
    )
    report = db.insert(
        "report",
        {
            "report_type": schedule["schedule_type"],
            "target": target,
            "title": f"{schedule['name']} fallback 리포트",
            "markdown": _build_report_markdown(schedule, stocks, price_result, error, global_news or {}),
            "codex_run_id": run["id"],
            "created_at": db.utc_now(),
        },
    )
    return {"run": run, "report": report, "analysis": {"major_signal_detected": False, "notification_summary": None}}


def _build_report_markdown(
    schedule: Dict[str, Any],
    stocks: List[Dict[str, Any]],
    price_result: Dict[str, Any],
    error: str,
    global_news: Dict[str, Any],
) -> str:
    from ..config import get_settings
    orch_label = get_settings().orchestrator_type.capitalize()

    # 분석 엔진 실패 시에는 잘못된 투자 판단을 만들지 않고 실패 원인만 전달한다.
    lines = [
        f"# {schedule['name']} 실행 결과",
        "",
        f"⚠️ **{orch_label} 분석에 실패했습니다.**",
        "",
        "## 오류 내용",
        f"```text\n{error}\n```",
        "",
        "## 다음 액션",
        "- 분석 엔진(Gemini/Codex)의 상태나 설정을 확인해 주세요.",
        "- 잠시 후 다시 시도하거나 수동으로 가격을 확인하시기 바랍니다.",
    ]
    return "\n".join(lines)


def _refresh_current_prices(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    updated = []
    failed = []
    kr_stocks = [stock for stock in stocks if stock["market"] == "KR"]
    by_ticker = {stock["ticker"]: stock for stock in kr_stocks}

    if kr_stocks:
        try:
            body = get_kis_client().inquire_domestic_prices(list(by_ticker.keys()))
            for item in body.get("items", []):
                ticker = item.get("ticker", "")
                stock = by_ticker.get(ticker)
                price = _to_float(item.get("current_price"))
                if not stock or price is None:
                    continue
                db.insert_price_snapshot(ticker, "KR", price, _to_float(item.get("volume")))
                updated.append({**stock, "price": price, "source": "kis"})
        except KisApiError as exc:
            failed.extend({**stock, "error": str(exc)} for stock in kr_stocks)

    for stock in stocks:
        if stock["market"] == "KR":
            continue
        latest = db.latest_price(stock["ticker"], stock["market"])
        if latest is None:
            failed.append({**stock, "error": "price provider is not connected for this market"})
        else:
            updated.append({**stock, "price": latest, "source": "local_snapshot"})

    return {"updated": updated, "failed": failed}


def _refresh_prices_for_schedule(schedule_type: str, stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if schedule_type in {"global_news_digest", "interest_area_research_watch"}:
        return _local_price_snapshots(stocks)
    return _refresh_current_prices(stocks)


def _local_price_snapshots(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    updated = []
    failed = []
    for stock in stocks:
        latest = db.latest_price(stock["ticker"], stock["market"])
        if latest is None:
            failed.append({**stock, "error": "local price snapshot is not available"})
        else:
            updated.append({**stock, "price": latest, "source": "local_snapshot"})
    return {"updated": updated, "failed": failed}


def _target_stocks(schedule: Dict[str, Any]) -> List[Dict[str, Any]]:
    if schedule["target_type"] == "interest":
        rows = db.list_rows("interest_stock")
    elif schedule["target_type"] == "holding":
        rows = db.list_rows("holding_stock")
    elif schedule["target_type"] == "tickers":
        tickers = schedule.get("tickers", [])
        if tickers:
            rows = [
                {"ticker": ticker, "market": "KR", "name": ticker}
                for ticker in tickers
            ]
        else:
            rows = [*db.list_rows("interest_stock"), *db.list_rows("holding_stock")]
    elif schedule["target_type"] == "areas" or schedule["schedule_type"] == "interest_area_research_watch":
        tickers = []
        for area in db.list_rows("interest_area"):
            if area.get("enabled"):
                tickers.extend(area.get("linked_tickers") or [])
        rows = [{"ticker": ticker, "market": "KR", "name": ticker} for ticker in tickers]
    else:
        rows = [*db.list_rows("interest_stock"), *db.list_rows("holding_stock")]

    deduped = {}
    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        market = str(row.get("market", "KR")).strip().upper()
        if not ticker:
            continue
        deduped[(market, ticker)] = {
            "ticker": ticker,
            "market": market,
            "name": row.get("name") or ticker,
        }
    return list(deduped.values())


def _schedule_target(schedule: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schedule_id": schedule["id"],
        "schedule_name": schedule["name"],
        "target_type": schedule["target_type"],
        "tickers": schedule.get("tickers") or [],
        "interest_area_ids": [
            area["id"] for area in db.list_rows("interest_area") if area.get("enabled")
        ] if schedule["schedule_type"] == "interest_area_research_watch" else [],
        "manual": True,
    }


def _should_notify_report(schedule: Dict[str, Any], result: Dict[str, Any]) -> bool:
    if schedule["schedule_type"] != "interest_area_research_watch":
        return True
    run = result.get("run") or {}
    analysis = result.get("analysis") or {}
    return run.get("status") != "completed" or bool(analysis.get("major_signal_detected"))


def _to_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_news_for_schedule(
    schedule: Dict[str, Any],
    enabled_sources: List[Dict[str, Any]],
    stocks: List[Dict[str, Any]],
    interest_areas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if schedule["schedule_type"] not in {"global_news_digest", "interest_area_research_watch"}:
        return {"items": [], "sources": [], "errors": [], "coverage_note": "News collection skipped for this schedule type."}
    return collect_global_news(enabled_sources, stocks, interest_areas)


def _build_global_news_fallback_sections(
    global_news: Dict[str, Any],
    stocks: List[Dict[str, Any]],
    price_result: Dict[str, Any],
) -> List[str]:
    news_items = global_news.get("items") or []
    risk_off_words = ("금리", "yield", "inflation", "인플레이션", "oil", "유가", "war", "전쟁", "하락", "fall", "slump", "tariff")
    risk_on_words = ("ai", "반도체", "hbm", "실적", "earnings", "rally", "상승", "수요", "demand", "cut", "인하", "stimulus")
    risk_off = _count_headline_words(news_items, risk_off_words)
    risk_on = _count_headline_words(news_items, risk_on_words)
    if risk_off > risk_on + 1:
        stance = "위험회피 우위"
        action = "추격매수보다 현금 비중과 손절 기준을 우선 확인하고, 금리 민감 성장주는 분할 접근만 허용합니다."
    elif risk_on > risk_off + 1:
        stance = "위험선호 우위"
        action = "AI/반도체와 실적 모멘텀이 확인되는 관심종목은 눌림목 분할매수 후보로 올리고, 약한 종목은 교체 후보로 둡니다."
    else:
        stance = "혼조"
        action = "방향성이 갈린 장세로 보고 신규 진입은 작게 나누며, 보유종목은 실적·환율·금리 민감도에 따라 차등 대응합니다."

    lines = [
        "",
        "## 최종 투자 관점",
        "",
        f"- 판정: **{stance}**",
        f"- 액션: {action}",
        "- 근거 품질: RSS/search headline 기반이며, 원문과 공시 확인 전에는 포지션 크기를 보수적으로 둡니다.",
        "",
        "## 헤드라인 근거",
        "",
    ]
    if news_items:
        for item in news_items[:12]:
            published = f" ({item['published_at']})" if item.get("published_at") else ""
            lines.append(f"- [{item['title']}]({item['url']}) - {item['source']}{published}")
    else:
        lines.append("- 수집된 뉴스 헤드라인이 없습니다. 오늘은 신규 판단을 보류하고 가격/공시 기반 대응만 합니다.")

    lines.extend(["", "## 보유/관심종목 액션", ""])
    updated = {item["ticker"]: item for item in price_result.get("updated", [])}
    if stocks:
        for stock in stocks[:12]:
            price = updated.get(stock["ticker"], {}).get("price")
            price_text = f", 현재가 {price}" if price is not None else ""
            lines.append(f"- {stock['name']}({stock['ticker']}){price_text}: {stance} 환경에서는 기존 계획가와 손절가 기준으로 분할 대응합니다.")
    else:
        lines.append("- 연결된 보유/관심종목이 없어 시장/섹터 관점만 제공합니다.")

    from ..config import get_settings
    orch_label = get_settings().orchestrator_type.capitalize()
    lines.extend(
        [
            "",
            "## 리스크",
            "",
            f"- {orch_label} 심층 분석 실패로 헤드라인 간 인과관계와 원문 세부 수치는 제한적으로만 반영됐습니다.",
            "- 금리, 환율, 원자재, 반도체 뉴스가 같은 방향으로 확인될 때만 포지션을 키우는 쪽이 낫습니다.",
        ]
    )
    return lines


def _count_headline_words(news_items: List[Dict[str, Any]], words: tuple) -> int:
    count = 0
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        count += sum(1 for word in words if word.lower() in text)
    return count
