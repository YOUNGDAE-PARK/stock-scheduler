import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from . import db
from .config import get_settings
from .services.notifications import send_test_notification


BASE_DIR = Path(__file__).resolve().parents[2]
SKILL_PATH = BASE_DIR / "codex_skills" / "api-orchestrator" / "SKILL.md"
SCHEMA_PATH = BASE_DIR / "codex_schemas" / "api_orchestrator_action.schema.json"
KNOWN_EXPERT_SOURCES = {
    "오건영": {
        "name": "오건영 Facebook",
        "category": "macro",
        "url": "https://www.facebook.com/ohrang79",
        "platform": "facebook",
        "enabled": False,
        "trust_note": "오건영님 Facebook 후보 URL. 공식 여부를 사용자가 확인한 뒤 활성화한다.",
    }
}
KNOWN_STOCKS = {
    "삼성전자": {"ticker": "005930", "market": "KR", "name": "삼성전자"},
    "SK하이닉스": {"ticker": "000660", "market": "KR", "name": "SK하이닉스"},
    "ACE AI반도체TOP3+": {"ticker": "469150", "market": "KR", "name": "ACE AI반도체TOP3+"},
    "KODEX 200": {"ticker": "069500", "market": "KR", "name": "KODEX 200"},
    "KODEX 코스피100": {"ticker": "237350", "market": "KR", "name": "KODEX 코스피100"},
    "TIGER K방산&우주": {"ticker": "463250", "market": "KR", "name": "TIGER K방산&우주"},
    "ACE KRX금현물": {"ticker": "411060", "market": "KR", "name": "ACE KRX금현물"},
    "ACE 미국나스닥100": {"ticker": "367380", "market": "KR", "name": "ACE 미국나스닥100"},
    "TIGER 미국S&P500": {"ticker": "360750", "market": "KR", "name": "TIGER 미국S&P500"},
    "KODEX 코스닥150": {"ticker": "229200", "market": "KR", "name": "KODEX 코스닥150"},
    "SOL 미국AI전력인프라": {"ticker": "486450", "market": "KR", "name": "SOL 미국AI전력인프라"},
    "토모큐브": {"ticker": "475960", "market": "KR", "name": "토모큐브"},
    "KODEX 코스닥150레버리지": {"ticker": "233740", "market": "KR", "name": "KODEX 코스닥150레버리지"},
    "두산에너빌리티": {"ticker": "034020", "market": "KR", "name": "두산에너빌리티"},
    "SOL 미국양자컴퓨팅TOP10": {"ticker": "0023A0", "market": "KR", "name": "SOL 미국양자컴퓨팅TOP10"},
}


class OrchestratorError(RuntimeError):
    pass


def parse_and_execute(text: str, execute: bool = True) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {
            "status": "needs_confirmation",
            "intent": "empty",
            "message": "명령 내용이 비어 있습니다.",
            "result": None,
        }
    try:
        plan = plan_command(text)
    except OrchestratorError as exc:
        return {
            "status": "needs_confirmation",
            "intent": "orchestrator_error",
            "message": f"Orchestrator가 요청을 해석하지 못했습니다. 조금 더 구체적으로 말해주세요. ({exc})",
            "result": None,
        }
    return execute_plan(plan, execute=execute)


def plan_command(text: str) -> Dict[str, Any]:
    prompt = build_prompt(text)
    settings = get_settings()
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as output:
        output_path = Path(output.name)
    try:
        is_gemini = settings.orchestrator_type.lower() == "gemini"
        args = [settings.gemini_bin if is_gemini else settings.codex_bin]

        if is_gemini:
            args.extend(["-p", prompt, "--output-format", "json", "--approval-mode", "plan"])
        else:
            args.extend([
                "exec",
                "--cd", str(BASE_DIR),
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--output-schema", str(SCHEMA_PATH),
                "--output-last-message", str(output_path),
                prompt
            ])

        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            input="",
            text=True,
            timeout=180,
            start_new_session=True,
            cwd=str(BASE_DIR) if is_gemini else None
        )

        if completed.returncode != 0:
            raise OrchestratorError(_summarize_orchestrator_error(completed.stderr or completed.stdout or "orchestrator exec failed"))

        if is_gemini:
            raw = completed.stdout.strip()
            if not raw:
                raise OrchestratorError("empty gemini response")
            try:
                # 1. 전체 응답 파싱
                full_data = json.loads(raw)
                # 2. response 필드 추출 (Gemini CLI 특성)
                inner_raw = full_data.get("response", "").strip()

                import re
                json_matches = re.findall(r"\{.*\}", inner_raw, re.DOTALL)
                if json_matches:
                    plan = json.loads(json_matches[-1])
                else:
                    plan = json.loads(inner_raw)

                # 필수 필드 보정
                if "action" not in plan and "intent" in plan:
                    plan["action"] = plan["intent"]
                return _normalize_orchestrator_plan(plan)
            except (json.JSONDecodeError, KeyError, AttributeError):
                # 구형 파싱 방식 유지 (폴백)
                import re
                json_matches = re.findall(r"\{.*\}", raw, re.DOTALL)
                if not json_matches:
                    raise OrchestratorError("no JSON found in gemini output")
                plan = json.loads(json_matches[-1])
                # 만약 파싱된 결과에 response가 있다면 한 번 더 시도
                if "response" in plan and isinstance(plan["response"], str):
                    try:
                        inner_raw = plan["response"].strip()
                        inner_matches = re.findall(r"\{.*\}", inner_raw, re.DOTALL)
                        if inner_matches:
                            plan = json.loads(inner_matches[-1])
                    except:
                        pass

                if "action" not in plan and "intent" in plan:
                    plan["action"] = plan["intent"]
                return _normalize_orchestrator_plan(plan)
        else:
            raw = output_path.read_text(encoding="utf-8").strip()
            if not raw:
                raise OrchestratorError("empty codex response")
            return _normalize_orchestrator_plan(json.loads(raw))
    except subprocess.TimeoutExpired as exc:
        raise OrchestratorError("orchestrator exec timeout") from exc
    except json.JSONDecodeError as exc:
        raise OrchestratorError("orchestrator response was not valid JSON") from exc
    finally:
        output_path.unlink(missing_ok=True)


def build_prompt(text: str) -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    capabilities = (BASE_DIR / "docs" / "API.md").read_text(encoding="utf-8")
    return f"""
You are the stock_scheduler API orchestrator. Your task is to map user natural language into structured JSON actions.

### INSTRUCTIONS
1. Follow the <skill> exactly.
2. Use the <api_docs> as the source of truth for supported actions.
3. Your output MUST be a SINGLE JSON object matching the required schema.
4. DO NOT include any text before or after the JSON object.
5. DO NOT use markdown code blocks (```json) for the JSON itself.
6. Infer ticker/market/quantity/price as per the examples.

<skill>
{skill}
</skill>

<api_docs>
{capabilities}
</api_docs>

User request:
{text}

Return ONLY the JSON object.
""".strip()


def execute_plan(plan: Dict[str, Any], execute: bool = True) -> Dict[str, Any]:
    action = plan.get("action")
    status = plan.get("status")
    message = plan.get("message") or ""
    slots = plan.get("slots") or {}

    if status == "unsupported" or action == "unsupported":
        return {
            "status": "unsupported",
            "intent": plan.get("intent") or "unknown",
            "message": message or "해당 기능은 아직 없습니다.",
            "result": None,
        }

    if status == "needs_confirmation" or action == "guide":
        expert_source = _known_expert_source(slots)
        if expert_source:
            return _create_expert_source(
                {**slots, **expert_source},
                message or "오건영 Facebook 후보 URL을 비활성 전문가 소스로 등록했습니다. 공식 여부를 확인한 뒤 활성화해주세요.",
            )
        return {
            "status": "needs_confirmation",
            "intent": plan.get("intent") or action or "guide",
            "message": message or "필요한 정보가 부족합니다.",
            "result": {"slots": slots} if slots else None,
        }

    handlers = _action_handlers()
    handler = handlers.get(action)
    if handler is None:
        return {
            "status": "unsupported",
            "intent": plan.get("intent") or action or "unknown",
            "message": message or "해당 기능은 아직 없습니다.",
            "result": None,
        }
    if not execute:
        return {
            "status": "needs_confirmation",
            "intent": plan.get("intent") or action,
            "message": message or "이 동작을 실행할까요?",
            "result": {"action": action, "slots": slots},
        }
    return handler(slots, message)


def _action_handlers() -> Dict[str, Any]:
    return {
        "create_interest": _create_interest,
        "list_interest": _list_interest,
        "delete_interest": _delete_interest,
        "create_holding": _create_holding,
        "list_holding": _list_holding,
        "delete_holding": _delete_holding,
        "create_interest_area": _create_interest_area,
        "list_interest_area": _list_interest_area,
        "delete_interest_area": _delete_interest_area,
        "create_expert_source": _create_expert_source,
        "list_expert_source": _list_expert_source,
        "delete_expert_source": _delete_expert_source,
        "list_schedule": _list_schedule,
        "test_notification": _test_notification,
        "run_analysis": _run_analysis,
        "batch": _execute_batch,
    }


def _execute_batch(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    items = _merge_batch_holdings(slots.get("items") or [])
    if not items:
        return _needs_slots("batch", "일괄 처리할 항목이 없습니다.")

    handlers = _action_handlers()
    executed = []
    failed = []
    for index, item in enumerate(items, start=1):
        action = item.get("action")
        item_slots = item.get("slots") or {}
        handler = handlers.get(action)
        if handler is None or action == "batch":
            failed.append({"index": index, "action": action, "message": "지원하지 않는 일괄 action입니다."})
            continue
        result = handler(item_slots, "")
        if result.get("status") == "executed":
            executed.append({"index": index, "action": action, "result": result.get("result")})
        else:
            failed.append({"index": index, "action": action, "message": result.get("message"), "result": result.get("result")})

    status = "executed" if executed else "needs_confirmation"
    summary = f"{message} 실제 저장 {len(executed)}건." if message else f"일괄 명령 {len(executed)}건을 처리했습니다."
    if failed:
        summary = f"{summary} 확인 필요 {len(failed)}건이 있습니다."
    return {
        "status": status,
        "intent": "batch",
        "message": summary,
        "result": {"executed": executed, "failed": failed, "executed_count": len(executed), "failed_count": len(failed)},
    }


def _merge_batch_holdings(items: list) -> list:
    merged = []
    holding_indexes = {}
    for item in items:
        if item.get("action") != "create_holding":
            merged.append(item)
            continue
        slots = _resolve_stock_slots(dict(item.get("slots") or {}))
        key = (slots.get("ticker"), slots.get("market"))
        if not key[0] or not key[1]:
            merged.append(item)
            continue
        if key not in holding_indexes:
            holding_indexes[key] = len(merged)
            merged.append({**item, "slots": slots})
            continue

        existing = merged[holding_indexes[key]]
        existing_slots = existing["slots"]
        previous_quantity = float(existing_slots.get("quantity") or 0)
        next_quantity = float(slots.get("quantity") or 0)
        total_quantity = previous_quantity + next_quantity
        if total_quantity > 0:
            previous_price = float(existing_slots.get("avg_price") or 0)
            next_price = float(slots.get("avg_price") or previous_price)
            existing_slots["avg_price"] = ((previous_price * previous_quantity) + (next_price * next_quantity)) / total_quantity
        existing_slots["quantity"] = total_quantity
        existing_slots["memo"] = _join_memo(existing_slots.get("memo"), slots.get("memo"))
    return merged


def _join_memo(first: Optional[str], second: Optional[str]) -> str:
    parts = [part for part in [first, second] if part]
    return " / ".join(dict.fromkeys(parts))


def _required(slots: Dict[str, Any], *keys: str) -> Optional[str]:
    missing = [key for key in keys if slots.get(key) in (None, "")]
    if missing:
        return ", ".join(missing)
    return None


def _slot_bool(slots: Dict[str, Any], key: str, default: bool) -> bool:
    value = slots.get(key)
    if value is None:
        return default
    return bool(value)


def _stock_payload(slots: Dict[str, Any]) -> Dict[str, Any]:
    slots = _resolve_stock_slots(slots)
    return {
        "ticker": slots["ticker"],
        "market": slots["market"],
        "name": slots.get("name") or slots["ticker"],
    }


def _resolve_stock_slots(slots: Dict[str, Any]) -> Dict[str, Any]:
    name = str(slots.get("name") or "").strip()
    known = KNOWN_STOCKS.get(name)
    if not known:
        return slots
    return {**slots, **known}


def _create_interest(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    slots = _resolve_stock_slots(slots)
    missing = _required(slots, "ticker", "market")
    if missing:
        return _needs_slots("create_interest", f"관심종목 추가에 필요한 정보가 부족합니다: {missing}")
    payload = {
        **_stock_payload(slots),
        "tags": slots.get("tags") or [],
        "memo": slots.get("memo") or "",
        "enabled": _slot_bool(slots, "enabled", True),
        "alert_settings": slots.get("alert_settings") or {},
    }
    result = db.insert("interest_stock", payload)
    return _executed("create_interest", message or f"{result['name']}({result['ticker']})를 관심종목에 추가했습니다.", result)


def _list_interest(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    rows = _filter_by_ticker(db.list_rows("interest_stock"), slots.get("ticker"))
    return _executed("list_interest", message or f"관심종목 조회 결과 {len(rows)}건입니다.", {"items": rows})


def _delete_interest(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    missing = _required(slots, "ticker")
    if missing:
        return _needs_slots("delete_interest", "삭제할 관심종목 ticker가 필요합니다.")
    deleted = _delete_by_ticker("interest_stock", slots["ticker"])
    return _executed("delete_interest", message or f"관심종목 {len(deleted)}건을 삭제했습니다.", {"deleted": deleted})


def _create_holding(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    slots = _resolve_stock_slots(slots)
    missing = _required(slots, "ticker", "market", "quantity", "avg_price")
    if missing:
        return _needs_slots("create_holding", f"보유종목 등록에 필요한 정보가 부족합니다: {missing}")
    payload = {
        **_stock_payload(slots),
        "quantity": float(slots["quantity"]),
        "avg_price": float(slots["avg_price"]),
        "buy_date": slots.get("buy_date"),
        "target_price": slots.get("target_price"),
        "stop_loss_price": slots.get("stop_loss_price"),
        "memo": slots.get("memo") or "",
        "enabled": _slot_bool(slots, "enabled", True),
        "alert_settings": slots.get("alert_settings") or {},
    }
    existing = _first_by_ticker_and_market("holding_stock", payload["ticker"], payload["market"]) or _first_by_name_and_market(
        "holding_stock", payload["name"], payload["market"]
    )
    if existing:
        result = db.update_row("holding_stock", existing["id"], payload)
        return _executed("create_holding", message or f"{result['name']} 보유종목을 업데이트했습니다.", result)
    result = db.insert("holding_stock", payload)
    return _executed("create_holding", message or f"{result['name']} 보유종목을 등록했습니다.", result)


def _list_holding(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    rows = _filter_by_ticker(db.list_rows("holding_stock"), slots.get("ticker"))
    return _executed("list_holding", message or f"보유종목 조회 결과 {len(rows)}건입니다.", {"items": rows})


def _delete_holding(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    missing = _required(slots, "ticker")
    if missing:
        return _needs_slots("delete_holding", "삭제할 보유종목 ticker가 필요합니다.")
    deleted = _delete_by_ticker("holding_stock", slots["ticker"])
    return _executed("delete_holding", message or f"보유종목 {len(deleted)}건을 삭제했습니다.", {"deleted": deleted})


def _create_interest_area(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    missing = _required(slots, "name")
    if missing:
        return _needs_slots("create_interest_area", "관심분야 이름이 필요합니다.")
    payload = {
        "name": slots["name"],
        "category": slots.get("category") or "research",
        "keywords": slots.get("keywords") or [],
        "linked_tickers": [str(ticker).strip().upper() for ticker in (slots.get("linked_tickers") or []) if str(ticker).strip()],
        "memo": slots.get("memo") or "",
        "enabled": _slot_bool(slots, "enabled", True),
    }
    existing = _first_interest_area(payload["name"])
    if existing:
        result = db.update_row("interest_area", existing["id"], payload)
        return _executed("create_interest_area", message or f"{result['name']} 관심분야를 업데이트했습니다.", result)
    result = db.insert("interest_area", payload)
    return _executed("create_interest_area", message or f"{result['name']} 관심분야를 추가했습니다.", result)


def _delete_interest_area(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    missing = _required(slots, "name")
    if missing:
        return _needs_slots("delete_interest_area", "삭제할 관심분야 이름이 필요합니다.")
    deleted = []
    for row in db.list_rows("interest_area"):
        if row.get("name") == slots["name"]:
            db.delete_row("interest_area", row["id"])
            deleted.append(row)
    return _executed("delete_interest_area", message or f"관심분야 {len(deleted)}건을 삭제했습니다.", {"deleted": deleted})


def _create_expert_source(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    missing = _required(slots, "name", "url")
    if missing:
        return _needs_slots("create_expert_source", "전문가 소스 등록에는 이름과 사용자가 확인한 공식 URL이 필요합니다.")
    payload = {
        "name": slots["name"],
        "category": slots.get("category") or "macro",
        "url": slots["url"],
        "platform": slots.get("platform") or "web",
        "enabled": _slot_bool(slots, "enabled", False),
        "trust_note": slots.get("trust_note") or "사용자 확인 전까지 비활성 상태로 등록",
        "last_checked_at": slots.get("last_checked_at"),
    }
    existing = _first_expert_source(payload["name"], payload["url"])
    if existing:
        return _executed("create_expert_source", message or f"{existing['name']} 전문가 소스가 이미 등록되어 있습니다.", existing)
    result = db.insert("expert_source", payload)
    return _executed("create_expert_source", message or f"{result['name']} 전문가 소스를 등록했습니다.", result)


def _list_expert_source(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    rows = db.list_rows("expert_source")
    return _executed("list_expert_source", message or f"전문가/뉴스 소스 조회 결과 {len(rows)}건입니다.", {"items": rows})


def _delete_expert_source(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    if not slots.get("name") and not slots.get("url"):
        return _needs_slots("delete_expert_source", "삭제할 경제뉴스 소스의 이름이나 URL이 필요합니다.")
    deleted = []
    for row in db.list_rows("expert_source"):
        name_matches = slots.get("name") and row.get("name") == slots["name"]
        url_matches = slots.get("url") and row.get("url") == slots["url"]
        if name_matches or url_matches:
            db.delete_row("expert_source", row["id"])
            deleted.append(row)
    return _executed("delete_expert_source", message or f"경제뉴스 소스 {len(deleted)}건을 삭제했습니다.", {"deleted": deleted})


def _list_interest_area(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    rows = db.list_rows("interest_area")
    return _executed("list_interest_area", message or f"관심분야 조회 결과 {len(rows)}건입니다.", {"items": rows})


def _list_schedule(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    rows = db.list_rows("schedule")
    return _executed("list_schedule", message or f"스케줄 조회 결과 {len(rows)}건입니다.", {"items": rows})


def _test_notification(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    result = send_test_notification(
        slots.get("target") or "galaxy-s24",
        slots.get("title") or "stock_scheduler 테스트 알림",
        slots.get("body") or "자연어 명령으로 알림을 보냈습니다.",
        slots.get("payload") or {"source": "command"},
    )
    return _executed("test_notification", message or "테스트 알림을 처리했습니다.", result)


def _run_analysis(slots: Dict[str, Any], message: str) -> Dict[str, Any]:
    missing = _required(slots, "ticker", "market")
    if missing:
        return _needs_slots("run_analysis", f"분석 실행에 필요한 정보가 부족합니다: {missing}")
    target = _stock_payload(slots)

    # 실제 분석 실행을 위해 context 구성
    stocks = [target]
    context = {
        "schedule": {"name": "자연어 명령 분석", "schedule_type": "manual_codex_analysis"},
        "target": target,
        "stocks": stocks,
        "prices": {"updated": stocks, "failed": []},
        "enabled_sources": [source for source in db.list_rows("expert_source") if source.get("enabled")],
        "global_news": {"items": [], "sources": [], "errors": []},
    }

    try:
        from .services.codex_runner import run_codex_schedule_analysis
        result = run_codex_schedule_analysis("manual_codex_analysis", target, context)
        run = result["run"]
        return _executed("run_analysis", message or f"{target['name']}({target['ticker']}) 분석을 완료했습니다.", run)
    except Exception as exc:
        # 실패 시 dry-run으로 기록
        from .services.codex_runner import run_dry_analysis
        result = run_dry_analysis("manual_codex_analysis", target, "final-investment-opinion")
        run = result["run"]
        return _executed("run_analysis", message or f"{target['name']}({target['ticker']}) 분석 중 오류가 발생하여 드라이 런으로 기록했습니다. ({exc})", run)


def _filter_by_ticker(rows: list, ticker: Optional[str]) -> list:
    if not ticker:
        return rows
    return [row for row in rows if row.get("ticker") == ticker]


def _first_by_ticker_and_market(table: str, ticker: str, market: str) -> Optional[Dict[str, Any]]:
    rows = [
        row
        for row in db.list_rows(table)
        if row.get("ticker") == ticker and row.get("market") == market
    ]
    return rows[0] if rows else None


def _first_by_name_and_market(table: str, name: str, market: str) -> Optional[Dict[str, Any]]:
    normalized = name.strip().lower()
    rows = [
        row
        for row in db.list_rows(table)
        if str(row.get("name", "")).strip().lower() == normalized and row.get("market") == market
    ]
    return rows[0] if rows else None


def _first_expert_source(name: str, url: str) -> Optional[Dict[str, Any]]:
    for row in db.list_rows("expert_source"):
        if row.get("name") == name or row.get("url") == url:
            return row
    return None


def _first_interest_area(name: str) -> Optional[Dict[str, Any]]:
    normalized = name.strip().lower()
    for row in db.list_rows("interest_area"):
        if str(row.get("name", "")).strip().lower() == normalized:
            return row
    return None


def _known_expert_source(slots: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = str(slots.get("name") or "")
    for keyword, source in KNOWN_EXPERT_SOURCES.items():
        if keyword in name:
            return source
    return None


def _delete_by_ticker(table: str, ticker: str) -> list:
    rows = _filter_by_ticker(db.list_rows(table), ticker)
    for row in rows:
        db.delete_row(table, row["id"])
    return rows


def _executed(intent: str, message: str, result: Any) -> Dict[str, Any]:
    return {"status": "executed", "intent": intent, "message": message, "result": result}


def _needs_slots(intent: str, message: str) -> Dict[str, Any]:
    return {"status": "needs_confirmation", "intent": intent, "message": message, "result": None}


def _summarize_orchestrator_error(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    usage_limit = next((line for line in lines if "usage limit" in line.lower()), "")
    if usage_limit:
        return usage_limit
    error_line = next((line for line in lines if line.lower().startswith("error")), "")
    if error_line:
        return error_line[:500]
    return (lines[-1] if lines else "orchestrator exec failed")[:500]


def _normalize_orchestrator_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(plan or {})
    normalized["status"] = normalized.get("status") or "needs_confirmation"
    normalized["intent"] = normalized.get("intent") or normalized.get("action") or "unknown"
    normalized["action"] = normalized.get("action") or "guide"
    normalized["message"] = normalized.get("message") or ""

    slots = normalized.get("slots")
    if not isinstance(slots, dict):
        slots = {}
    slots.setdefault("ticker", None)
    slots.setdefault("market", None)
    slots.setdefault("name", None)
    slots.setdefault("quantity", None)
    slots.setdefault("avg_price", None)
    slots.setdefault("buy_date", None)
    slots.setdefault("target_price", None)
    slots.setdefault("stop_loss_price", None)
    slots.setdefault("tags", [])
    slots.setdefault("keywords", [])
    slots.setdefault("linked_tickers", [])
    slots.setdefault("memo", None)
    slots.setdefault("url", None)
    slots.setdefault("platform", None)
    slots.setdefault("category", None)
    slots.setdefault("enabled", None)
    slots.setdefault("target", None)
    slots.setdefault("title", None)
    slots.setdefault("body", None)
    payload = slots.get("payload")
    if not isinstance(payload, dict):
        payload = {"source": None}
    payload.setdefault("source", None)
    slots["payload"] = payload
    slots.setdefault("items", None)

    if isinstance(slots.get("items"), list):
        normalized_items = []
        for item in slots["items"]:
            item = dict(item or {})
            item["action"] = item.get("action")
            item_slots = item.get("slots")
            if not isinstance(item_slots, dict):
                item_slots = {}
            item_slots.setdefault("ticker", None)
            item_slots.setdefault("market", None)
            item_slots.setdefault("name", None)
            item_slots.setdefault("quantity", None)
            item_slots.setdefault("avg_price", None)
            item_slots.setdefault("buy_date", None)
            item_slots.setdefault("target_price", None)
            item_slots.setdefault("stop_loss_price", None)
            item_slots.setdefault("tags", [])
            item_slots.setdefault("keywords", [])
            item_slots.setdefault("linked_tickers", [])
            item_slots.setdefault("memo", None)
            item_slots.setdefault("url", None)
            item_slots.setdefault("platform", None)
            item_slots.setdefault("category", None)
            item_slots.setdefault("enabled", None)
            item_slots.setdefault("target", None)
            item_slots.setdefault("title", None)
            item_slots.setdefault("body", None)
            item_payload = item_slots.get("payload")
            if not isinstance(item_payload, dict):
                item_payload = {"source": None}
            item_payload.setdefault("source", None)
            item_slots["payload"] = item_payload
            item["slots"] = item_slots
            normalized_items.append(item)
        slots["items"] = normalized_items

    normalized["slots"] = slots
    return normalized
