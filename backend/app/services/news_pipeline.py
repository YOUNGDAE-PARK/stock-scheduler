from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import db
from .news import collect_global_news, fetch_article_body


POSITIVE_KEYWORDS = (
    "상승",
    "호재",
    "수혜",
    "확대",
    "증가",
    "성장",
    "강세",
    "surge",
    "gain",
    "beat",
    "strong",
    "record",
)
NEGATIVE_KEYWORDS = (
    "하락",
    "악재",
    "둔화",
    "감소",
    "우려",
    "약세",
    "충격",
    "리스크",
    "fall",
    "drop",
    "miss",
    "weak",
    "cut",
    "tariff",
)
SECTOR_KEYWORDS = {
    "semiconductor": ("반도체", "hbm", "memory", "chip", "semiconductor", "sk hynix", "nvidia"),
    "ai": ("ai", "인공지능", "온디바이스", "gpu", "데이터센터", "llm"),
    "macro": ("금리", "yield", "inflation", "인플레이션", "연준", "federal reserve", "환율", "oil", "유가"),
    "battery": ("2차전지", "배터리", "battery", "ev"),
    "bio": ("바이오", "bio", "임상", "clinical", "drug"),
    "defense": ("방산", "defense", "missile", "shipbuilding"),
    "energy": ("원전", "전력", "energy", "nuclear", "gas", "lng"),
}
HIGH_IMPORTANCE_KEYWORDS = (
    "실적",
    "guidance",
    "금리",
    "관세",
    "규제",
    "정책",
    "인수",
    "합병",
    "투자",
    "earnings",
    "fed",
    "rate",
)
PIPELINE_REPORT_TYPES = {
    "interest_area_radar_report": "interest_area_radar",
    "interest_stock_radar_report": "interest_stock_radar",
}
PIPELINE_STAGES = ("news_collect", "article_fetch", "news_classify", "market_cluster")
INITIAL_BACKFILL_DAYS = 7
PIPELINE_RUN_LOCK = threading.Lock()


def run_news_collection(max_items: int = 36) -> Dict[str, Any]:
    enabled_sources = [source for source in db.list_rows("expert_source") if source.get("enabled")]
    interest_stocks = [stock for stock in db.list_rows("interest_stock") if stock.get("enabled")]
    holdings = [stock for stock in db.list_rows("holding_stock") if stock.get("enabled")]
    interest_areas = [area for area in db.list_rows("interest_area") if area.get("enabled")]
    stocks = _dedupe_stock_rows([*interest_stocks, *holdings])
    result = collect_global_news(enabled_sources, stocks, interest_areas, max_items=max_items)
    state = db.get_pipeline_state("news_collect") or {}
    state_meta = state.get("meta") or {}
    source_last_collected_at = dict(state_meta.get("source_last_collected_at") or {})

    existing_urls = {str(row.get("url") or "").strip() for row in db.list_rows("news_raw") if row.get("url")}
    existing_hashes = {str(row.get("content_hash") or "") for row in db.list_rows("news_raw")}
    inserted = 0
    skipped = 0
    filtered_out = 0
    inserted_ids = []
    next_source_last_collected_at = dict(source_last_collected_at)
    now_iso = db.utc_now()
    for item in result.get("items") or []:
        source_key = str(item.get("source_key") or item.get("source") or "unknown")
        cutoff = _collection_cutoff(source_last_collected_at.get(source_key))
        published_at = _parse_datetime(item.get("published_at"))
        if published_at is not None and published_at <= cutoff:
            filtered_out += 1
            continue
        content_hash = _content_hash(item)
        url = str(item.get("url") or "").strip()
        if (url and url in existing_urls) or content_hash in existing_hashes:
            skipped += 1
            if source_key not in next_source_last_collected_at:
                next_source_last_collected_at[source_key] = now_iso
            continue
        row = db.insert(
            "news_raw",
            {
                "title": item.get("title") or "",
                "url": url,
                "source": item.get("source") or "",
                "category": item.get("category") or "news",
                "published_at": item.get("published_at") or "",
                "collected_at": db.utc_now(),
                "raw_summary": item.get("summary") or "",
                "content_hash": content_hash,
                "raw_payload": item,
            },
        )
        inserted += 1
        inserted_ids.append(row["id"])
        if url:
            existing_urls.add(url)
        existing_hashes.add(content_hash)
        next_source_last_collected_at[source_key] = _max_timestamp_iso(
            next_source_last_collected_at.get(source_key),
            item.get("published_at") or now_iso,
        )

    for source in result.get("sources") or []:
        source_key = str(source.get("feed_id") or source.get("name") or "unknown")
        next_source_last_collected_at.setdefault(source_key, now_iso)

    result_payload = {
        "status": "completed",
        "inserted": inserted,
        "skipped": skipped,
        "filtered_out": filtered_out,
        "errors": result.get("errors") or [],
        "sources": result.get("sources") or [],
        "news_raw_ids": inserted_ids,
        "source_last_collected_at": next_source_last_collected_at,
        "initial_backfill_days": INITIAL_BACKFILL_DAYS,
    }
    db.upsert_pipeline_state(
        "news_collect",
        {
            "status": "completed",
            "last_finished_at": now_iso,
            "last_error": None,
            "last_cursor": str(max(inserted_ids)) if inserted_ids else state.get("last_cursor"),
            "meta": result_payload,
        },
    )
    return result_payload


def classify_news(limit: int = 80) -> Dict[str, Any]:
    raw_rows = sorted(db.list_rows("news_raw"), key=lambda row: row["id"])
    refined_rows = db.list_rows("news_refined")
    refined_by_raw_id = {row.get("news_raw_id") for row in refined_rows}
    stock_universe = _stock_universe()
    interest_areas = [area for area in db.list_rows("interest_area") if area.get("enabled")]
    interest_stocks = [stock for stock in db.list_rows("interest_stock") if stock.get("enabled")]
    holdings = [stock for stock in db.list_rows("holding_stock") if stock.get("enabled")]

    inserted = 0
    inserted_ids = []
    for raw in raw_rows:
        if raw["id"] in refined_by_raw_id:
            continue
        text = " ".join(
            part.strip()
            for part in [
                str(raw.get("title") or ""),
                str(raw.get("raw_summary") or ""),
                str(raw.get("raw_body") or ""),
            ]
            if str(part or "").strip()
        ).strip()
        tickers, matched_stocks = _extract_tickers(text, stock_universe)
        sectors = _extract_sectors(text)
        user_links = _build_user_links(text, matched_stocks, interest_stocks, holdings, interest_areas)
        importance = _importance_score(text, user_links)
        sentiment = _sentiment(text)
        row = db.insert(
            "news_refined",
            {
                "news_raw_id": raw["id"],
                "tickers": tickers,
                "sectors": sectors,
                "importance": importance,
                "sentiment": sentiment,
                "user_links": user_links,
                "refined_summary": raw.get("raw_summary") or raw.get("title") or "",
                "classified_at": db.utc_now(),
            },
        )
        inserted += 1
        inserted_ids.append(row["id"])
        if inserted >= limit:
            break

    return {"status": "completed", "inserted": inserted, "news_refined_ids": inserted_ids}


def run_article_fetch(limit: int = 24) -> Dict[str, Any]:
    raw_rows = sorted(db.list_rows("news_raw"), key=lambda row: row["id"])
    fetched = 0
    skipped = 0
    failed = 0
    fetched_ids = []
    enriched_ids = []
    errors = []

    for raw in raw_rows:
        if fetched >= limit:
            break

        url = str(raw.get("url") or "").strip()
        payload = dict(raw.get("raw_payload") or {})
        attempts = int(payload.get("article_fetch_attempts") or 0)
        previous_resolved_url = str(payload.get("article_fetch_resolved_url") or "")
        previous_resolved_host = previous_resolved_url.split("/")[2] if "://" in previous_resolved_url else ""
        should_retry_google_stub = (
            not raw.get("raw_body")
            and previous_resolved_host == "news.google.com"
            and payload.get("article_fetch_last_error") in (None, "", "empty_body")
        )

        if raw.get("raw_body"):
            skipped += 1
            continue
        if not url:
            payload["article_fetch_attempted"] = True
            payload["article_fetch_attempts"] = attempts + 1
            payload["article_fetch_last_error"] = "missing_url"
            payload["article_fetch_last_attempted_at"] = db.utc_now()
            db.update_row(
                "news_raw",
                raw["id"],
                {
                    "raw_payload": payload,
                },
            )
            skipped += 1
            continue
        if attempts >= 3 and not should_retry_google_stub:
            skipped += 1
            continue

        try:
            result = fetch_article_body(url)
            body_text = result.get("body") or ""
            payload.update(
                {
                    "article_fetch_attempted": True,
                    "article_fetch_attempts": attempts + 1,
                    "article_fetch_last_error": None if body_text else "empty_body",
                    "article_fetch_last_attempted_at": db.utc_now(),
                    "article_fetch_resolved_url": result.get("resolved_url") or url,
                    "article_fetch_source_url": result.get("source_url") or url,
                    "article_fetch_content_type": result.get("content_type") or "",
                }
            )
            updated = db.update_row(
                "news_raw",
                raw["id"],
                {
                    "raw_body": body_text,
                    "raw_payload": payload,
                },
            )
            fetched += 1
            fetched_ids.append(raw["id"])
            if (updated or {}).get("raw_body"):
                enriched_ids.append(raw["id"])
            if updated and not updated.get("raw_body"):
                errors.append({"id": raw["id"], "url": url, "error": "empty_body"})
        except Exception as exc:
            payload.update(
                {
                    "article_fetch_attempted": True,
                    "article_fetch_attempts": attempts + 1,
                    "article_fetch_last_error": str(exc),
                    "article_fetch_last_attempted_at": db.utc_now(),
                }
            )
            db.update_row(
                "news_raw",
                raw["id"],
                {
                    "raw_payload": payload,
                },
            )
            failed += 1
            errors.append({"id": raw["id"], "url": url, "error": str(exc)})

    deleted_refined = 0
    deleted_clusters = 0
    if enriched_ids:
        enriched_id_set = set(enriched_ids)
        for row in db.list_rows("news_refined"):
            if row.get("news_raw_id") in enriched_id_set and db.delete_row("news_refined", row["id"]):
                deleted_refined += 1
        for row in db.list_rows("news_cluster"):
            related = set(row.get("related_news_ids") or [])
            if related & enriched_id_set and db.delete_row("news_cluster", row["id"]):
                deleted_clusters += 1

    return {
        "status": "completed",
        "fetched": fetched,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "news_raw_ids": fetched_ids,
        "enriched_news_raw_ids": enriched_ids,
        "deleted_refined": deleted_refined,
        "deleted_clusters": deleted_clusters,
    }


def cluster_news(window_hours: int = 24, max_clusters: int = 12) -> Dict[str, Any]:
    cutoff = _utc_cutoff(window_hours)
    raw_map = {row["id"]: row for row in db.list_rows("news_raw")}
    refined_rows = [
        row
        for row in db.list_rows("news_refined")
        if _parse_datetime(row.get("classified_at")) and _parse_datetime(row.get("classified_at")) >= cutoff
    ]
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in refined_rows:
        raw = raw_map.get(row.get("news_raw_id"))
        group_key = _cluster_key(row, raw)
        groups[group_key].append(row)

    existing_keys = {
        (
            str(row.get("cluster_key") or ""),
            tuple(row.get("related_news_ids") or []),
        )
        for row in db.list_rows("news_cluster")
    }
    inserted = 0
    inserted_ids = []
    for cluster_key, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:max_clusters]:
        related_news_ids = sorted({row["news_raw_id"] for row in members if row.get("news_raw_id")})
        dedupe_key = (cluster_key, tuple(related_news_ids))
        if dedupe_key in existing_keys:
            continue
        sectors = sorted({sector for row in members for sector in (row.get("sectors") or [])})
        tickers = sorted({ticker for row in members for ticker in (row.get("tickers") or [])})
        titles = [raw_map[row["news_raw_id"]]["title"] for row in members if raw_map.get(row["news_raw_id"])]
        narrative = _build_cluster_narrative(cluster_key, titles, members)
        row = db.insert(
            "news_cluster",
            {
                "cluster_key": cluster_key,
                "theme": cluster_key.replace("_", " "),
                "narrative": narrative,
                "related_news_ids": related_news_ids,
                "tickers": tickers,
                "sectors": sectors,
                "importance_score": max((row.get("importance") or 1) for row in members),
                "cluster_window_start": cutoff.isoformat(),
                "cluster_window_end": db.utc_now(),
            },
        )
        inserted += 1
        inserted_ids.append(row["id"])
        existing_keys.add(dedupe_key)

    return {"status": "completed", "inserted": inserted, "news_cluster_ids": inserted_ids}


def purge_pipeline_data(days: int = 30) -> Dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    deleted = {
        "news_raw": db.delete_older_than("news_raw", "created_at", cutoff),
        "news_refined": db.delete_older_than("news_refined", "created_at", cutoff),
        "news_cluster": db.delete_older_than("news_cluster", "created_at", cutoff),
        "strategy_report": db.delete_older_than("strategy_report", "created_at", cutoff),
    }
    return {"status": "completed", "cutoff": cutoff, "deleted": deleted}


def run_news_pipeline_chain(force_collect: bool = False) -> Dict[str, Any]:
    if not PIPELINE_RUN_LOCK.acquire(blocking=False):
        return {
            "status": "skipped",
            "reason": "pipeline_running",
            "collect": {"status": "skipped"},
            "fetch": {"status": "skipped"},
            "classify": {"status": "skipped"},
            "cluster": {"status": "skipped"},
        }

    try:
        stages = _resume_stages(force_collect=force_collect)
        results: Dict[str, Any] = {}
        if not stages:
            return {
                "status": "skipped",
                "reason": "pipeline_up_to_date",
                "collect": {"status": "skipped"},
                "fetch": {"status": "skipped"},
                "classify": {"status": "skipped"},
                "cluster": {"status": "skipped"},
            }

        for stage in stages:
            db.upsert_pipeline_state(
                stage,
                {
                    "status": "running",
                    "last_started_at": db.utc_now(),
                    "last_error": None,
                    "meta": {"trigger": "chain"},
                },
            )
            try:
                if stage == "news_collect":
                    result = run_news_collection()
                elif stage == "article_fetch":
                    result = run_article_fetch()
                elif stage == "news_classify":
                    result = classify_news()
                else:
                    result = cluster_news()
                db.upsert_pipeline_state(
                    stage,
                    {
                        "status": "completed",
                        "last_finished_at": db.utc_now(),
                        "last_error": None,
                        "last_cursor": _stage_cursor(stage, result),
                        "meta": result,
                    },
                )
                results[_stage_result_key(stage)] = result
            except Exception as exc:
                db.upsert_pipeline_state(
                    stage,
                    {
                        "status": "failed",
                        "last_finished_at": db.utc_now(),
                        "last_error": str(exc),
                        "meta": {"trigger": "chain"},
                    },
                )
                raise

        for stage in PIPELINE_STAGES:
            results.setdefault(_stage_result_key(stage), {"status": "skipped"})
        results["status"] = "completed"
        results["started_from"] = stages[0]
        return results
    finally:
        PIPELINE_RUN_LOCK.release()


def pipeline_is_stale(hours: int = 4) -> bool:
    rows = db.list_rows("news_raw")
    if not rows:
        return True
    latest = max((_parse_datetime(row.get("created_at")) for row in rows), default=None)
    if latest is None:
        return True
    return latest < _utc_cutoff(hours)


def warm_strategy_pipeline(force_collect: bool = False) -> Dict[str, Any]:
    return run_news_pipeline_chain(force_collect=force_collect)


def build_strategy_context(
    schedule_type: str,
    schedule: Dict[str, Any],
    target: Dict[str, Any],
    stocks: List[Dict[str, Any]],
    price_result: Dict[str, Any],
) -> Dict[str, Any]:
    report_type = PIPELINE_REPORT_TYPES[schedule_type]
    recent_clusters = _recent_rows("news_cluster", "created_at", 24)
    recent_refined = _recent_rows("news_refined", "classified_at", 24)
    raw_map = {row["id"]: row for row in db.list_rows("news_raw")}
    interest_areas = [area for area in db.list_rows("interest_area") if area.get("enabled")]
    interest_stocks = [stock for stock in db.list_rows("interest_stock") if stock.get("enabled")]
    holdings = [stock for stock in db.list_rows("holding_stock") if stock.get("enabled")]

    context = {
        "schedule": schedule,
        "target": target,
        "report_type": report_type,
        "stocks": stocks,
        "prices": price_result,
        "interest_areas": interest_areas,
        "interest_stocks": interest_stocks,
        "holdings": holdings,
        "pipeline": {
            "recent_clusters": recent_clusters,
            "recent_refined_news": _refined_news_context(recent_refined, raw_map),
            "recent_headlines": _headline_summaries(recent_refined, raw_map),
        },
        "strategy_view": _strategy_view(report_type, recent_clusters, recent_refined, raw_map, interest_areas, interest_stocks, holdings, price_result),
        "provider_notes": {
            "news_pipeline": "Raw news is stored in news_raw, then classified and summarized into news_refined, clustered into news_cluster, and the final report primarily consumes refined and clustered data.",
            "raw_news_limit": "Article title and body are used during refinement. Final strategy analysis should rely on refined summaries, tags, and clusters rather than raw article text alone.",
        },
    }
    return context


def mirror_strategy_report(
    report_type: str,
    schedule_id: int,
    report: Dict[str, Any],
    analysis: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    cluster_ids = [row["id"] for row in (context.get("pipeline", {}).get("recent_clusters") or [])[:10]]
    return db.insert(
        "strategy_report",
        {
            "report_type": report_type,
            "schedule_id": schedule_id,
            "title": report.get("title") or "",
            "markdown": report.get("markdown") or "",
            "decision_json": analysis.get("decision_json") or {},
            "major_signal_detected": bool(analysis.get("major_signal_detected")),
            "notification_summary": analysis.get("notification_summary"),
            "source_cluster_ids": cluster_ids,
        },
    )


def fallback_strategy_analysis(report_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
    view = context.get("strategy_view") or {}
    items = view.get("items") or []
    title = "관심분야 Radar" if report_type == "interest_area_radar" else "관심종목 Radar"
    heading = "관심분야 Radar" if report_type == "interest_area_radar" else "관심종목 Radar"
    lines = [f"# {heading}", "", "## 주요 포인트"]
    for item in items[:8]:
        lines.append(f"- {item['label']}: {item['summary']}")
    if not items:
        lines.append("- 최근 연결 뉴스가 많지 않아 기본 감시 모드로 유지합니다.")
    lines.extend(["", "## 감시 포인트"])
    for point in view.get("watch_points") or ["정책, 금리, 실적 이벤트를 우선 확인합니다."]:
        lines.append(f"- {point}")
    return {
        "title": title,
        "markdown": "\n".join(lines),
        "major_signal_detected": any(item.get("importance", 0) >= 4 for item in items[:3]),
        "notification_summary": items[0]["label"] if items else heading,
        "decision_json": {"items": items[:8]},
    }


def _stock_universe() -> List[Dict[str, str]]:
    seen = set()
    rows = [*db.list_rows("interest_stock"), *db.list_rows("holding_stock")]
    universe = []
    for row in rows:
        key = (row.get("market"), row.get("ticker"))
        if key in seen:
            continue
        seen.add(key)
        universe.append({"ticker": row.get("ticker") or "", "market": row.get("market") or "KR", "name": row.get("name") or row.get("ticker") or ""})
    return universe


def _extract_tickers(text: str, stock_universe: Sequence[Dict[str, str]]) -> Tuple[List[str], List[Dict[str, str]]]:
    lowered = text.lower()
    matched = []
    for stock in stock_universe:
        ticker = str(stock.get("ticker") or "").upper()
        name = str(stock.get("name") or "")
        if ticker and ticker.lower() in lowered:
            matched.append(stock)
            continue
        if name and name.lower() in lowered:
            matched.append(stock)
    deduped = {(stock["market"], stock["ticker"]): stock for stock in matched}
    matched_stocks = list(deduped.values())
    return [stock["ticker"] for stock in matched_stocks], matched_stocks


def _extract_sectors(text: str) -> List[str]:
    lowered = text.lower()
    sectors = [sector for sector, keywords in SECTOR_KEYWORDS.items() if any(keyword.lower() in lowered for keyword in keywords)]
    return sectors or ["general"]


def _build_user_links(
    text: str,
    matched_stocks: Sequence[Dict[str, str]],
    interest_stocks: Sequence[Dict[str, Any]],
    holdings: Sequence[Dict[str, Any]],
    interest_areas: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    lowered = text.lower()
    stock_keys = {(stock["market"], stock["ticker"]) for stock in matched_stocks}

    linked_interest_stocks = []
    for stock in interest_stocks:
        if (stock.get("market"), stock.get("ticker")) in stock_keys:
            linked_interest_stocks.append({"id": stock["id"], "ticker": stock["ticker"], "name": stock["name"], "reason": "headline mentions watchlist stock"})

    linked_holdings = []
    for holding in holdings:
        if (holding.get("market"), holding.get("ticker")) in stock_keys:
            linked_holdings.append({"id": holding["id"], "ticker": holding["ticker"], "name": holding["name"], "reason": "headline mentions holding stock"})

    linked_areas = []
    for area in interest_areas:
        reason_parts = []
        if str(area.get("name") or "").lower() in lowered:
            reason_parts.append("area name")
        for keyword in area.get("keywords") or []:
            if str(keyword).lower() in lowered:
                reason_parts.append(f"keyword:{keyword}")
        for ticker in area.get("linked_tickers") or []:
            if str(ticker).upper() in {stock["ticker"] for stock in matched_stocks}:
                reason_parts.append(f"linked_ticker:{ticker}")
        if reason_parts:
            linked_areas.append({"id": area["id"], "name": area["name"], "reason": ", ".join(reason_parts)})

    return {
        "interest_areas": linked_areas,
        "interest_stocks": linked_interest_stocks,
        "holdings": linked_holdings,
    }


def _importance_score(text: str, user_links: Dict[str, Any]) -> int:
    lowered = text.lower()
    score = 2
    if any(keyword.lower() in lowered for keyword in HIGH_IMPORTANCE_KEYWORDS):
        score += 2
    if any(user_links.get(key) for key in ("interest_areas", "interest_stocks", "holdings")):
        score += 1
    if any(keyword.lower() in lowered for keyword in ("급등", "plunge", "폭락", "earnings", "guidance", "실적")):
        score += 1
    return max(1, min(score, 5))


def _sentiment(text: str) -> str:
    lowered = text.lower()
    positive = sum(1 for keyword in POSITIVE_KEYWORDS if keyword.lower() in lowered)
    negative = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword.lower() in lowered)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _content_hash(item: Dict[str, Any]) -> str:
    source = "|".join(
        [
            str(item.get("title") or "").strip(),
            str(item.get("url") or "").strip(),
            str(item.get("published_at") or "").strip(),
        ]
    )
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


def _dedupe_stock_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        market = str(row.get("market") or "KR").strip().upper()
        if not ticker:
            continue
        deduped[(market, ticker)] = {"ticker": ticker, "market": market, "name": row.get("name") or ticker}
    return list(deduped.values())


def _cluster_key(row: Dict[str, Any], raw: Optional[Dict[str, Any]]) -> str:
    if row.get("sectors"):
        return str((row.get("sectors") or ["general"])[0])
    if row.get("tickers"):
        return f"ticker_{(row.get('tickers') or ['misc'])[0]}"
    return str((raw or {}).get("category") or "general")


def _build_cluster_narrative(cluster_key: str, titles: Sequence[str], members: Sequence[Dict[str, Any]]) -> str:
    tone = _group_sentiment(members)
    lead = titles[0] if titles else "headline flow is limited"
    return f"{cluster_key} narrative is {tone}. Representative headline: {lead}"


def _group_sentiment(members: Sequence[Dict[str, Any]]) -> str:
    counts = defaultdict(int)
    for row in members:
        counts[str(row.get("sentiment") or "neutral")] += 1
    if counts["positive"] > counts["negative"]:
        return "risk-on"
    if counts["negative"] > counts["positive"]:
        return "risk-off"
    return "mixed"


def _headline_summaries(refined_rows: Sequence[Dict[str, Any]], raw_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for row in refined_rows[:12]:
        raw = raw_map.get(row.get("news_raw_id"))
        if not raw:
            continue
        items.append(
            {
                "title": raw.get("title"),
                "source": raw.get("source"),
                "published_at": raw.get("published_at"),
                "importance": row.get("importance"),
                "sentiment": row.get("sentiment"),
                "tickers": row.get("tickers") or [],
                "sectors": row.get("sectors") or [],
            }
        )
    return items


def _refined_news_context(refined_rows: Sequence[Dict[str, Any]], raw_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for row in refined_rows[:12]:
        raw = raw_map.get(row.get("news_raw_id"))
        if not raw:
            continue
        items.append(
            {
                "news_raw_id": row.get("news_raw_id"),
                "title": raw.get("title"),
                "source": raw.get("source"),
                "published_at": raw.get("published_at"),
                "refined_summary": row.get("refined_summary") or raw.get("raw_summary") or raw.get("title") or "",
                "importance": row.get("importance"),
                "sentiment": row.get("sentiment"),
                "tickers": row.get("tickers") or [],
                "sectors": row.get("sectors") or [],
                "user_links": row.get("user_links") or {},
                "has_raw_body": bool(raw.get("raw_body")),
            }
        )
    return items


def _strategy_view(
    report_type: str,
    recent_clusters: Sequence[Dict[str, Any]],
    recent_refined: Sequence[Dict[str, Any]],
    raw_map: Dict[int, Dict[str, Any]],
    interest_areas: Sequence[Dict[str, Any]],
    interest_stocks: Sequence[Dict[str, Any]],
    holdings: Sequence[Dict[str, Any]],
    price_result: Dict[str, Any],
) -> Dict[str, Any]:
    if report_type == "interest_area_radar":
        return _interest_area_view(recent_clusters, recent_refined, interest_areas)
    return _interest_stock_view(recent_refined, raw_map, interest_stocks)


def _interest_area_view(
    recent_clusters: Sequence[Dict[str, Any]],
    recent_refined: Sequence[Dict[str, Any]],
    interest_areas: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    items = []
    watch_points = []
    for area in interest_areas:
        linked = []
        linked_tickers = {ticker.upper() for ticker in (area.get("linked_tickers") or [])}
        for cluster in recent_clusters:
            cluster_tickers = {ticker.upper() for ticker in (cluster.get("tickers") or [])}
            if linked_tickers & cluster_tickers:
                linked.append(cluster)
                continue
            narrative = str(cluster.get("narrative") or "").lower()
            if str(area.get("name") or "").lower() in narrative:
                linked.append(cluster)
        if linked:
            top = linked[0]
            items.append(
                {
                    "label": area["name"],
                    "summary": top.get("narrative") or top.get("theme") or "연결 뉴스 흐름이 감지되었습니다.",
                    "importance": int(top.get("importance_score") or 1),
                }
            )
        if area.get("keywords"):
            watch_points.append(f"{area['name']}: {', '.join(area.get('keywords')[:3])}")
    if not items:
        for row in recent_refined[:3]:
            linked_areas = row.get("user_links", {}).get("interest_areas") or []
            if linked_areas:
                items.append(
                    {
                        "label": linked_areas[0]["name"],
                        "summary": row.get("refined_summary") or "관심분야 연결 뉴스",
                        "importance": int(row.get("importance") or 1),
                    }
                )
    return {"items": items, "watch_points": watch_points[:6]}


def _interest_stock_view(
    recent_refined: Sequence[Dict[str, Any]],
    raw_map: Dict[int, Dict[str, Any]],
    interest_stocks: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    items = []
    watch_points = []
    for stock in interest_stocks:
        stock_ticker = str(stock.get("ticker") or "").upper()
        related = [row for row in recent_refined if stock_ticker in {ticker.upper() for ticker in (row.get("tickers") or [])}]
        if not related:
            continue
        related.sort(key=lambda row: (-int(row.get("importance") or 1), row["id"]))
        top = related[0]
        raw = raw_map.get(top.get("news_raw_id")) or {}
        items.append(
            {
                "label": stock["name"],
                "summary": top.get("refined_summary") or raw.get("title") or "관심종목 연결 뉴스",
                "importance": int(top.get("importance") or 1),
            }
        )
        watch_points.append(f"{stock['name']}: {top.get('sentiment')} / 중요도 {top.get('importance')}")
    return {"items": items[:8], "watch_points": watch_points[:8]}


def _recent_rows(table: str, field: str, hours: int) -> List[Dict[str, Any]]:
    cutoff = _utc_cutoff(hours)
    rows = []
    for row in db.list_rows(table):
        value = _parse_datetime(row.get(field))
        if value and value >= cutoff:
            rows.append(row)
    return rows


def _utc_cutoff(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _collection_cutoff(last_collected_at: Optional[str]) -> datetime:
    parsed = _parse_datetime(last_collected_at)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc) - timedelta(days=INITIAL_BACKFILL_DAYS)


def _max_timestamp_iso(existing: Optional[str], candidate: str) -> str:
    existing_dt = _parse_datetime(existing)
    candidate_dt = _parse_datetime(candidate)
    if existing_dt is None and candidate_dt is None:
        return candidate
    if existing_dt is None:
        return candidate
    if candidate_dt is None:
        return existing or candidate
    return candidate if candidate_dt >= existing_dt else (existing or candidate)


def _resume_stages(force_collect: bool = False) -> List[str]:
    if force_collect:
        return list(PIPELINE_STAGES)

    for stage in PIPELINE_STAGES:
        state = db.get_pipeline_state(stage)
        if state and state.get("status") == "running":
            return list(PIPELINE_STAGES[PIPELINE_STAGES.index(stage):])

    if pipeline_is_stale():
        return list(PIPELINE_STAGES)

    if _has_unfetched_article_bodies():
        return ["article_fetch", "news_classify", "market_cluster"]

    if _has_unclassified_news():
        return ["news_classify", "market_cluster"]

    if _needs_recluster():
        return ["market_cluster"]

    return []


def _has_unclassified_news() -> bool:
    refined_by_raw_id = {row.get("news_raw_id") for row in db.list_rows("news_refined")}
    return any(row["id"] not in refined_by_raw_id for row in db.list_rows("news_raw"))


def _has_unfetched_article_bodies() -> bool:
    for row in db.list_rows("news_raw"):
        if row.get("raw_body"):
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        payload = row.get("raw_payload") or {}
        attempts = int(payload.get("article_fetch_attempts") or 0)
        if attempts < 3:
            return True
    return False


def _needs_recluster() -> bool:
    refined_rows = db.list_rows("news_refined")
    if not refined_rows:
        return False
    latest_refined = max((_parse_datetime(row.get("classified_at")) for row in refined_rows), default=None)
    cluster_rows = db.list_rows("news_cluster")
    latest_cluster = max((_parse_datetime(row.get("created_at")) for row in cluster_rows), default=None) if cluster_rows else None
    if latest_refined is None:
        return False
    if latest_cluster is None:
        return True
    return latest_refined > latest_cluster


def _stage_cursor(stage: str, result: Dict[str, Any]) -> Optional[str]:
    if stage in {"news_collect", "article_fetch"}:
        ids = result.get("news_raw_ids") or []
    elif stage == "news_classify":
        ids = result.get("news_refined_ids") or []
    else:
        ids = result.get("news_cluster_ids") or []
    if not ids:
        return None
    return str(max(ids))


def _stage_result_key(stage: str) -> str:
    return {
        "news_collect": "collect",
        "article_fetch": "fetch",
        "news_classify": "classify",
        "market_cluster": "cluster",
    }[stage]
