import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .. import db
from ..config import get_settings


BASE_DIR = Path(__file__).resolve().parents[3]
SCHEDULE_ANALYSIS_SCHEMA_PATH = BASE_DIR / "codex_schemas" / "schedule_analysis.schema.json"
SCHEDULE_SKILLS = {
    "stock_report": BASE_DIR / "codex_skills" / "stock-report" / "SKILL.md",
    "global_news_digest": BASE_DIR / "codex_skills" / "macro-news-digest" / "SKILL.md",
    "manual_codex_analysis": BASE_DIR / "codex_skills" / "final-investment-opinion" / "SKILL.md",
    "interest_area_research_watch": BASE_DIR / "codex_skills" / "interest-area-research-watch" / "SKILL.md",
}

logger = logging.getLogger(__name__)


class OrchestratorAnalysisError(RuntimeError):
    pass


def run_dry_analysis(run_type: str, target: Dict[str, Any], agent_role: str) -> Dict[str, Any]:
    started = db.utc_now()
    run = db.insert(
        "codex_run",
        {
            "run_type": run_type,
            "target": target,
            "agent_role": agent_role,
            "prompt_path": "",
            "output_path": "",
            "status": "dry_run_completed",
            "started_at": started,
            "finished_at": db.utc_now(),
            "error": None,
        },
    )
    title = f"{agent_role} dry-run report"
    markdown = "\n".join(
        [
            "# Dry-run 투자 의견",
            "",
            "- 결론: 보유",
            "- 핵심 근거: 실제 Codex CLI 연동 전 dry-run 결과입니다.",
            "- 반대 근거: 시장 데이터와 뉴스 수집이 아직 연결되지 않았습니다.",
            "- 리스크: 외부 provider 미연동 상태입니다.",
            "- 확인할 뉴스/공시/SNS: 데이터 수집 adapter 구현 후 보강합니다.",
            "- 다음 액션 기준: 실제 provider와 Codex output schema를 연결합니다.",
        ]
    )
    report = db.insert(
        "report",
        {
            "report_type": run_type,
            "target": target,
            "title": title,
            "markdown": markdown,
            "codex_run_id": run["id"],
            "created_at": db.utc_now(),
        },
    )
    return {"run": run, "report": report}


def _get_orchestrator_cmd() -> List[str]:
    settings = get_settings()
    if settings.orchestrator_type.lower() == "gemini":
        return [settings.gemini_bin]
    return [settings.codex_bin]


def run_codex_schedule_analysis(run_type: str, target: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    started = db.utc_now()
    skill_path = _schedule_skill_path(run_type)
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as output:
        output_path = Path(output.name)

    run = db.insert(
        "codex_run",
        {
            "run_type": run_type,
            "target": target,
            "agent_role": "schedule-analysis",
            "prompt_path": str(skill_path),
            "output_path": str(output_path),
            "status": "running",
            "started_at": started,
            "finished_at": None,
            "error": None,
        },
    )
    try:
        cmd = _get_orchestrator_cmd()
        is_gemini = "gemini" in cmd[0].lower()
        settings = get_settings()
        prompt = _build_schedule_analysis_prompt(context, skill_path, compact=is_gemini)

        args = [*cmd]
        if is_gemini:
            # Gemini CLI: keep headless JSON mode, avoid extra planning mode latency.
            args.extend(["-p", prompt, "--output-format", "json"])
        else:
            # Codex CLI: codex exec ...
            args.extend([
                "exec",
                "--cd", str(BASE_DIR),
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--output-schema", str(SCHEDULE_ANALYSIS_SCHEMA_PATH),
                "--output-last-message", str(output_path),
                prompt
            ])

        logger.info(
            "schedule analysis start run_id=%s orchestrator=%s run_type=%s target=%s skill=%s stocks=%s news_items=%s",
            run["id"],
            settings.orchestrator_type,
            run_type,
            json.dumps(target, ensure_ascii=False),
            str(skill_path),
            len(context.get("stocks") or []),
            len((context.get("global_news") or {}).get("items") or []),
        )
        logger.info(
            "schedule analysis command run_id=%s args=%s",
            run["id"],
            json.dumps(args[:-1] + ["<prompt omitted>"], ensure_ascii=False),
        )

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

        logger.info(
            "schedule analysis completed run_id=%s returncode=%s stdout_summary=%s stderr_summary=%s",
            run["id"],
            completed.returncode,
            _truncate_log_text(completed.stdout),
            _truncate_log_text(completed.stderr),
        )

        if completed.returncode != 0:
            raise OrchestratorAnalysisError(_summarize_codex_error(completed.stderr or completed.stdout or "orchestrator exec failed"))

        if is_gemini:
            # Gemini는 stdout에서 JSON을 읽음
            raw = completed.stdout.strip()
            if not raw:
                raise OrchestratorAnalysisError("empty gemini response")
            try:
                import re
                # 1. 전체 응답 파싱
                full_data = json.loads(raw)
                # 2. response 필드 추출 (Gemini CLI 특성)
                inner_raw = full_data.get("response", "").strip()

                # 3. response 필드 내의 JSON 추출 및 파싱
                json_matches = re.findall(r"\{.*\}", inner_raw, re.DOTALL)
                if json_matches:
                    parsed = json.loads(json_matches[-1])
                else:
                    # 필드가 직접 JSON이 아닐 경우 전체 response 시도
                    parsed = json.loads(inner_raw)
            except (json.JSONDecodeError, KeyError, AttributeError):
                # 구형 파싱 방식 유지 (폴백)
                json_matches = re.findall(r"\{.*\}", raw, re.DOTALL)
                if not json_matches:
                    raise OrchestratorAnalysisError("no JSON found in gemini output")
                parsed = json.loads(json_matches[-1])
                # 만약 파싱된 결과에 response가 있다면 한 번 더 시도
                if "response" in parsed and isinstance(parsed["response"], str):
                    try:
                        inner_raw = parsed["response"].strip()
                        inner_matches = re.findall(r"\{.*\}", inner_raw, re.DOTALL)
                        if inner_matches:
                            parsed = json.loads(inner_matches[-1])
                    except:
                        pass
        else:
            # Codex는 지정된 파일에서 읽음
            raw = output_path.read_text(encoding="utf-8").strip()
            if not raw:
                raise OrchestratorAnalysisError("empty codex response")
            parsed = json.loads(raw)

        parsed = _normalize_analysis_payload(parsed)

        run = db.update_row(
            "codex_run",
            run["id"],
            {"status": "completed", "finished_at": db.utc_now(), "error": None},
        )

        logger.info(
            "schedule analysis parsed run_id=%s title=%s major_signal_detected=%s",
            run["id"],
            parsed.get("title") or parsed.get("subject") or f"{run_type} report",
            parsed.get("major_signal_detected"),
        )

        # 필드 유무 확인 및 기본값 처리
        title = parsed["title"]
        markdown = parsed["markdown"]

        report = db.insert(
            "report",
            {
                "report_type": run_type,
                "target": target,
                "title": title,
                "markdown": markdown,
                "codex_run_id": run["id"],
                "created_at": db.utc_now(),
            },
        )
        return {"run": run, "report": report, "analysis": parsed}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OrchestratorAnalysisError, OSError) as exc:
        logger.exception(
            "schedule analysis failed run_id=%s run_type=%s target=%s",
            run["id"],
            run_type,
            json.dumps(target, ensure_ascii=False),
        )
        run = db.update_row(
            "codex_run",
            run["id"],
            {"status": "failed", "finished_at": db.utc_now(), "error": str(exc)},
        )
        raise OrchestratorAnalysisError(str(exc)) from exc
    finally:
        output_path.unlink(missing_ok=True)


def _build_schedule_analysis_prompt(context: Dict[str, Any], skill_path: Path, compact: bool = False) -> str:
    skill = skill_path.read_text(encoding="utf-8")
    serialized_context = (
        json.dumps(_compact_schedule_context(context), ensure_ascii=False, separators=(",", ":"))
        if compact
        else json.dumps(context, ensure_ascii=False, indent=2)
    )
    extra_rule = (
        "6. Keep the response concise and prioritize the most recent and most relevant headlines only.\n"
        if compact
        else ""
    )
    return f"""
You are a stock market analyst. Your task is to generate a structured report in JSON format.

### INSTRUCTIONS
1. Follow the provided <skill> exactly to analyze the <context>.
2. Your output MUST be a SINGLE JSON object matching this schema:
   - "title": A concise title for the report.
   - "markdown": The full report content in Korean Markdown.
   - "major_signal_detected": (boolean) True if an urgent signal is found.
   - "notification_summary": (string) A short summary for mobile notifications.
3. DO NOT include any text before or after the JSON object.
4. DO NOT use markdown code blocks (```json) for the JSON itself.
5. ENSURE the "markdown" field is NOT EMPTY and contains the full analysis.
{extra_rule}

<skill>
{skill}
</skill>

<context>
{serialized_context}
</context>

Return ONLY the JSON object.
""".strip()


def _summarize_codex_error(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    usage_limit = next((line for line in lines if "usage limit" in line.lower()), "")
    if usage_limit:
        return usage_limit
    error_line = next((line for line in lines if line.lower().startswith("error")), "")
    if error_line and error_line not in {"ERROR: {", "error: {"}:
        return error_line[:500]
    compact = _truncate_log_text(output, limit=500)
    if compact:
        return compact
    return (lines[-1] if lines else "codex exec failed")[:500]


def _truncate_log_text(text: str, limit: int = 500) -> str:
    if not text:
        return ""
    compact = " | ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _compact_schedule_context(context: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(context or {})
    compact["enabled_sources"] = [
        {
            "name": item.get("name"),
            "category": item.get("category"),
            "platform": item.get("platform"),
        }
        for item in (compact.get("enabled_sources") or [])[:6]
    ]
    compact["stocks"] = [
        {
            "ticker": item.get("ticker"),
            "market": item.get("market"),
            "name": item.get("name"),
        }
        for item in (compact.get("stocks") or [])[:8]
    ]
    compact["interest_areas"] = [
        {
            "name": item.get("name"),
            "category": item.get("category"),
            "keywords": (item.get("keywords") or [])[:5],
            "linked_tickers": (item.get("linked_tickers") or [])[:5],
        }
        for item in (compact.get("interest_areas") or [])[:5]
    ]
    prices = dict(compact.get("prices") or {})
    prices["updated"] = [
        {
            "ticker": item.get("ticker"),
            "market": item.get("market"),
            "name": item.get("name"),
            "price": item.get("price"),
        }
        for item in (prices.get("updated") or [])[:8]
    ]
    prices["failed"] = [
        {
            "ticker": item.get("ticker"),
            "market": item.get("market"),
            "name": item.get("name"),
            "error": item.get("error"),
        }
        for item in (prices.get("failed") or [])[:5]
    ]
    compact["prices"] = prices

    global_news = dict(compact.get("global_news") or {})
    news_items = []
    seen_titles = set()
    for item in global_news.get("items") or []:
        title = str(item.get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        news_items.append(
            {
                "title": title,
                "published_at": item.get("published_at"),
                "summary": item.get("summary"),
                "source": item.get("source"),
                "category": item.get("category"),
            }
        )
        if len(news_items) >= 10:
            break
    global_news["items"] = news_items
    global_news["sources"] = [
        {
            "name": item.get("name"),
            "category": item.get("category"),
        }
        for item in (global_news.get("sources") or [])[:6]
    ]
    global_news["errors"] = (global_news.get("errors") or [])[:5]
    compact["global_news"] = global_news
    return compact


def _normalize_analysis_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    normalized["title"] = str(
        normalized.get("title")
        or normalized.get("subject")
        or "schedule report"
    )
    normalized["markdown"] = str(
        normalized.get("markdown")
        or normalized.get("content")
        or normalized.get("body")
        or "No content generated."
    )
    normalized["major_signal_detected"] = bool(normalized.get("major_signal_detected", False))
    summary = normalized.get("notification_summary")
    normalized["notification_summary"] = None if summary in (None, "") else str(summary)
    return normalized


def _schedule_skill_path(run_type: str) -> Path:
    return SCHEDULE_SKILLS.get(run_type, BASE_DIR / "codex_skills" / "schedule-analysis" / "SKILL.md")
