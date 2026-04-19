import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

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


class CodexAnalysisError(RuntimeError):
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


def run_codex_schedule_analysis(run_type: str, target: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    started = db.utc_now()
    skill_path = _schedule_skill_path(run_type)
    prompt = _build_schedule_analysis_prompt(context, skill_path)
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
        completed = subprocess.run(
            [
                get_settings().codex_bin,
                "exec",
                "--cd",
                str(BASE_DIR),
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(SCHEDULE_ANALYSIS_SCHEMA_PATH),
                "--output-last-message",
                str(output_path),
                prompt,
            ],
            check=False,
            capture_output=True,
            input="",
            text=True,
            timeout=180,
            start_new_session=True,
        )
        if completed.returncode != 0:
            raise CodexAnalysisError(_summarize_codex_error(completed.stderr or completed.stdout or "codex exec failed"))
        raw = output_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise CodexAnalysisError("empty codex response")
        parsed = json.loads(raw)
        run = db.update_row(
            "codex_run",
            run["id"],
            {"status": "completed", "finished_at": db.utc_now(), "error": None},
        )
        report = db.insert(
            "report",
            {
                "report_type": run_type,
                "target": target,
                "title": parsed["title"],
                "markdown": parsed["markdown"],
                "codex_run_id": run["id"],
                "created_at": db.utc_now(),
            },
        )
        return {"run": run, "report": report, "analysis": parsed}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, CodexAnalysisError, OSError) as exc:
        run = db.update_row(
            "codex_run",
            run["id"],
            {"status": "failed", "finished_at": db.utc_now(), "error": str(exc)},
        )
        raise CodexAnalysisError(str(exc)) from exc
    finally:
        output_path.unlink(missing_ok=True)


def _build_schedule_analysis_prompt(context: Dict[str, Any], skill_path: Path) -> str:
    skill = skill_path.read_text(encoding="utf-8")
    return f"""
You are generating a stock_scheduler schedule analysis report.

Follow this skill exactly:

<skill>
{skill}
</skill>

Use only this JSON context:

<context>
{json.dumps(context, ensure_ascii=False, indent=2)}
</context>

Return only a JSON object matching the schema.
""".strip()


def _summarize_codex_error(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    usage_limit = next((line for line in lines if "usage limit" in line.lower()), "")
    if usage_limit:
        return usage_limit
    error_line = next((line for line in lines if line.lower().startswith("error")), "")
    if error_line:
        return error_line[:500]
    return (lines[-1] if lines else "codex exec failed")[:500]


def _schedule_skill_path(run_type: str) -> Path:
    return SCHEDULE_SKILLS.get(run_type, BASE_DIR / "codex_skills" / "schedule-analysis" / "SKILL.md")
