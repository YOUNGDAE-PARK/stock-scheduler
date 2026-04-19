def test_orchestrator_failure_does_not_fallback_to_regex(monkeypatch):
    import backend.app.command_parser as command_parser

    def fail_plan(text):
        raise command_parser.OrchestratorError("usage limit")

    monkeypatch.setattr(command_parser, "plan_command", fail_plan)

    result = command_parser.parse_and_execute("삼성전자 160500원 284주 보유", execute=False)

    assert result["status"] == "needs_confirmation"
    assert result["intent"] == "orchestrator_error"
    assert result["result"] is None
    assert "usage limit" in result["message"]
