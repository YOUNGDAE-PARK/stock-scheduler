
from unittest.mock import patch, MagicMock

def test_orchestrator_command_selection():
    from backend.app.command_parser import plan_command

    # 1. ORCHESTRATOR_TYPE=codex 테스트
    with patch("backend.app.command_parser.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            orchestrator_type="codex",
            codex_bin="/usr/bin/codex",
            gemini_bin="gemini",
            sqlite_path="stock_scheduler.db"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='{"action": "test"}')
            # 임시 파일에서 읽는 로직을 모킹하기 위해 tempfile.NamedTemporaryFile 등도 고려해야 하지만,
            # 여기서는 cmd 리스트의 첫 번째 인자만 확인
            try:
                plan_command("test")
            except:
                pass # JSON 파싱 에러 등은 무시 (cmd 확인이 목적)

            called_args = mock_run.call_args[0][0]
            assert called_args[0] == "/usr/bin/codex"

    # 2. ORCHESTRATOR_TYPE=gemini 테스트
    with patch("backend.app.command_parser.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            orchestrator_type="gemini",
            codex_bin="/usr/bin/codex",
            gemini_bin="/usr/local/bin/gemini",
            sqlite_path="stock_scheduler.db"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='{"action": "test"}')
            try:
                plan_command("test")
            except:
                pass

            called_args = mock_run.call_args[0][0]
            assert called_args[0] == "/usr/local/bin/gemini"

def test_codex_runner_command_selection():
    from backend.app.services.codex_runner import _get_orchestrator_cmd

    # 1. ORCHESTRATOR_TYPE=codex 테스트
    with patch("backend.app.services.codex_runner.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            orchestrator_type="codex",
            codex_bin="/usr/bin/codex",
            gemini_bin="gemini"
        )
        assert _get_orchestrator_cmd() == ["/usr/bin/codex"]

    # 2. ORCHESTRATOR_TYPE=gemini 테스트
    with patch("backend.app.services.codex_runner.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            orchestrator_type="gemini",
            codex_bin="/usr/bin/codex",
            gemini_bin="/usr/local/bin/gemini"
        )
        assert _get_orchestrator_cmd() == ["/usr/local/bin/gemini"]


def test_gemini_plan_is_normalized():
    from backend.app.command_parser import _normalize_orchestrator_plan

    plan = _normalize_orchestrator_plan(
        {
            "status": "executed",
            "intent": "create_holding",
            "action": "create_holding",
            "message": "ok",
            "slots": {
                "ticker": "005930",
                "market": "KR",
                "name": "삼성전자",
                "quantity": 1,
                "avg_price": 70000,
            },
        }
    )

    assert plan["slots"]["payload"] == {"source": None}
    assert plan["slots"]["items"] is None
    assert plan["slots"]["tags"] == []
    assert plan["slots"]["keywords"] == []
    assert plan["slots"]["linked_tickers"] == []


def test_gemini_analysis_payload_is_normalized():
    from backend.app.services.codex_runner import _normalize_analysis_payload

    payload = _normalize_analysis_payload(
        {
            "title": "테스트 리포트",
            "markdown": "# 테스트",
        }
    )

    assert payload["title"] == "테스트 리포트"
    assert payload["markdown"] == "# 테스트"
    assert payload["major_signal_detected"] is False
    assert payload["notification_summary"] is None
    assert payload["decision_json"] == {
        "items": [],
        "watch_points": [],
        "notes": [],
        "summary": None,
    }
