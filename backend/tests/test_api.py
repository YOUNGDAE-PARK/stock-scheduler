import importlib

from fastapi.testclient import TestClient


def make_client(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("NOTIFICATION_MODE", "dry-run")

    import backend.app.config as config
    import backend.app.db as db
    import backend.app.main as main

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(main)
    return TestClient(main.app)


def stub_plan(monkeypatch, plan):
    import backend.app.command_parser as command_parser

    monkeypatch.setattr(command_parser, "plan_command", lambda text: plan)


def test_interest_crud(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        created = client.post(
            "/api/interests",
            json={"ticker": "005930", "market": "KR", "name": "삼성전자", "tags": ["반도체"]},
        )
        assert created.status_code == 200
        assert created.json()["ticker"] == "005930"

        listed = client.get("/api/interests")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        row_id = created.json()["id"]
        patched = client.patch(f"/api/interests/{row_id}", json={"memo": "관찰"})
        assert patched.status_code == 200
        assert patched.json()["memo"] == "관찰"

        deleted = client.delete(f"/api/interests/{row_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}


def test_codex_diagnostics_reports_auth_file(monkeypatch, tmp_path):
    auth_home = tmp_path / "codex-home"
    auth_home.mkdir()
    (auth_home / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(auth_home))

    with make_client(monkeypatch, tmp_path) as client:
        response = client.get("/api/diagnostics/codex")

    assert response.status_code == 200
    body = response.json()
    assert body["codex_home"] == str(auth_home)
    assert body["auth_json_exists"] is True


def test_interest_area_crud_and_seed_schedule(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        schedules = client.get("/api/schedules").json()
        research_watch = next(item for item in schedules if item["schedule_type"] == "interest_area_research_watch")
        assert research_watch["cron"] == "매일 09:00 KST"
        assert research_watch["target_type"] == "areas"

        created = client.post(
            "/api/interest-areas",
            json={
                "name": "AI 반도체",
                "category": "research",
                "keywords": ["HBM", "온디바이스 AI"],
                "linked_tickers": ["005930", "000660"],
                "memo": "연결 종목 전망에 영향이 큰 연구성과만 알림",
            },
        )
        assert created.status_code == 200
        assert created.json()["name"] == "AI 반도체"
        assert created.json()["linked_tickers"] == ["005930", "000660"]

        listed = client.get("/api/interest-areas")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        deleted = client.delete(f"/api/interest-areas/{created.json()['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}


def test_holding_validation(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/api/holdings",
            json={"ticker": "TSLA", "market": "US", "name": "Tesla", "quantity": 3, "avg_price": 180},
        )
        assert response.status_code == 200
        assert response.json()["quantity"] == 3

        invalid = client.post(
            "/api/holdings",
            json={"ticker": "TSLA", "market": "US", "name": "Tesla", "quantity": 0, "avg_price": 180},
        )
        assert invalid.status_code == 422


def test_command_executes_known_interest(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "create_interest",
                "action": "create_interest",
                "message": "삼성전자를 관심종목에 추가했습니다.",
                "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자"},
            },
        )
        response = client.post("/api/commands", json={"text": "삼성전자 관심종목 추가"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "executed"
        assert body["intent"] == "create_interest"

        interests = client.get("/api/interests").json()
        assert interests[0]["ticker"] == "005930"


def test_common_list_commands_use_codex_orchestrator(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "list_interest",
                "action": "list_interest",
                "message": "관심종목 현황입니다.",
                "slots": {},
            },
        )

        interest = client.post("/api/commands", json={"text": "관심종목 현황"})
        assert interest.status_code == 200
        assert interest.json()["status"] == "executed"
        assert interest.json()["intent"] == "list_interest"

        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "list_schedule",
                "action": "list_schedule",
                "message": "스케줄 현황입니다.",
                "slots": {},
            },
        )
        schedule = client.post("/api/commands", json={"text": "스케줄 목록 보여줘"})
        assert schedule.status_code == 200
        assert schedule.json()["intent"] == "list_schedule"

        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "list_interest_area",
                "action": "list_interest_area",
                "message": "관심분야 현황입니다.",
                "slots": {},
            },
        )
        areas = client.post("/api/commands", json={"text": "관심분야 리스트"})
        assert areas.status_code == 200
        assert areas.json()["intent"] == "list_interest_area"


def test_holding_label_command_requests_missing_details(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "needs_confirmation",
                "intent": "create_holding",
                "action": "guide",
                "message": "보유종목 등록에는 수량과 평균매수가가 필요합니다.",
                "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자"},
            },
        )
        response = client.post("/api/commands", json={"text": "보유종목: 삼성전자"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "needs_confirmation"
        assert body["intent"] == "create_holding"
        assert "수량과 평균매수가" in body["message"]
        assert body["result"]["slots"]["ticker"] == "005930"

        holdings = client.get("/api/holdings").json()
        assert holdings == []


def test_command_orchestrates_holding_create_list_and_delete(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        plans = iter(
            [
                {
                    "status": "executed",
                    "intent": "create_holding",
                    "action": "create_holding",
                    "message": "삼성전자 보유종목을 등록했습니다.",
                    "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자", "quantity": 3, "avg_price": 70000},
                },
                {
                    "status": "executed",
                    "intent": "list_holding",
                    "action": "list_holding",
                    "message": "보유종목 조회 결과입니다.",
                    "slots": {"ticker": "005930"},
                },
                {
                    "status": "executed",
                    "intent": "delete_holding",
                    "action": "delete_holding",
                    "message": "삼성전자 보유종목을 삭제했습니다.",
                    "slots": {"ticker": "005930"},
                },
            ]
        )
        import backend.app.command_parser as command_parser
        monkeypatch.setattr(command_parser, "plan_command", lambda text: next(plans))

        created = client.post(
            "/api/commands",
            json={"text": "삼성전자 3주 평균가 70000원으로 보유종목 등록"},
        )
        assert created.status_code == 200
        assert created.json()["status"] == "executed"
        assert created.json()["intent"] == "create_holding"

        listed = client.post("/api/commands", json={"text": "보유종목 삼성전자 보여줘"})
        assert listed.status_code == 200
        assert listed.json()["intent"] == "list_holding"
        assert listed.json()["result"]["items"][0]["ticker"] == "005930"

        deleted = client.post("/api/commands", json={"text": "삼성전자 보유종목 삭제"})
        assert deleted.status_code == 200
        assert deleted.json()["intent"] == "delete_holding"
        assert len(deleted.json()["result"]["deleted"]) == 1


def test_command_infers_holding_create_from_natural_held_phrase(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        plans = iter(
            [
                {
                    "status": "executed",
                    "intent": "create_holding",
                    "action": "create_holding",
                    "message": "삼성전자 보유종목을 등록했습니다.",
                    "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자", "quantity": 284, "avg_price": 160500},
                },
                {
                    "status": "executed",
                    "intent": "create_holding",
                    "action": "create_holding",
                    "message": "삼성전자 보유종목을 업데이트했습니다.",
                    "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자", "quantity": 300, "avg_price": 150000},
                },
            ]
        )
        import backend.app.command_parser as command_parser
        monkeypatch.setattr(command_parser, "plan_command", lambda text: next(plans))

        created = client.post(
            "/api/commands",
            json={"text": "삼성전자 160500원 284주 보유"},
        )
        assert created.status_code == 200
        body = created.json()
        assert body["status"] == "executed"
        assert body["intent"] == "create_holding"
        assert body["result"]["ticker"] == "005930"
        assert body["result"]["avg_price"] == 160500
        assert body["result"]["quantity"] == 284

        updated = client.post(
            "/api/commands",
            json={"text": "삼성전자 150000원 300주 보유"},
        )
        assert updated.status_code == 200
        updated_body = updated.json()
        assert updated_body["status"] == "executed"
        assert updated_body["result"]["id"] == body["result"]["id"]
        assert updated_body["result"]["avg_price"] == 150000
        assert updated_body["result"]["quantity"] == 300

        holdings = client.get("/api/holdings").json()
        assert len(holdings) == 1
        assert holdings[0]["ticker"] == "005930"


def test_command_orchestrates_holding_add_phrase(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "create_holding",
                "action": "create_holding",
                "message": "삼성전자 보유종목을 등록했습니다.",
                "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자", "quantity": 284, "avg_price": 16500},
            },
        )

        response = client.post(
            "/api/commands",
            json={"text": "삼성전자 16500원 284주 보유종목에 추가"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "executed"
        assert body["intent"] == "create_holding"
        assert body["result"]["ticker"] == "005930"
        assert body["result"]["quantity"] == 284
        assert body["result"]["avg_price"] == 16500


def test_command_orchestrates_batch_holding_create(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "batch_holding_create",
                "action": "batch",
                "message": "보유종목을 일괄 등록합니다.",
                "slots": {
                    "items": [
                        {
                            "action": "create_holding",
                            "slots": {
                                "ticker": "069500",
                                "market": "KR",
                                "name": "KODEX 200",
                                "quantity": 613,
                                "avg_price": 94050,
                                "memo": "현재주가 기준 임시 평균단가",
                            },
                        },
                        {
                            "action": "create_holding",
                            "slots": {
                                "ticker": "091160",
                                "market": "KR",
                                "name": "KODEX 코스피100",
                                "quantity": 494,
                                "avg_price": 74665,
                                "memo": "현재주가 기준 임시 평균단가",
                            },
                        },
                    ]
                },
            },
        )

        response = client.post(
            "/api/commands",
            json={"text": "KODEX 200: 보유수량 613 / 현재주가 94050\nKODEX 코스피100: 보유수량 494 / 현재주가 74665"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "executed"
        assert body["intent"] == "batch"
        assert body["result"]["executed_count"] == 2

        holdings = client.get("/api/holdings").json()
        assert len(holdings) == 2
        assert {item["ticker"] for item in holdings} == {"069500", "237350"}


def test_batch_holding_create_merges_duplicate_tickers(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "batch_holding_create",
                "action": "batch",
                "message": "보유종목을 일괄 등록합니다.",
                "slots": {
                    "items": [
                        {
                            "action": "create_holding",
                            "slots": {
                                "ticker": "411060",
                                "market": "KR",
                                "name": "ACE KRX금현물",
                                "quantity": 207,
                                "avg_price": 31850,
                                "memo": "일반 계좌",
                            },
                        },
                        {
                            "action": "create_holding",
                            "slots": {
                                "ticker": "999999",
                                "market": "KR",
                                "name": "ACE KRX금현물",
                                "quantity": 187,
                                "avg_price": 31850,
                                "memo": "[CMA] 계좌",
                            },
                        },
                    ]
                },
            },
        )

        response = client.post(
            "/api/commands",
            json={"text": "ACE KRX금현물 두 계좌 보유수량 일괄 등록"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["executed_count"] == 1

        holdings = client.get("/api/holdings").json()
        assert len(holdings) == 1
        assert holdings[0]["quantity"] == 394
        assert holdings[0]["avg_price"] == 31850
        assert "CMA" in holdings[0]["memo"]


def test_known_stock_name_corrects_orchestrator_ticker(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        first = client.post(
            "/api/holdings",
            json={"ticker": "449450", "market": "KR", "name": "TIGER K방산&우주", "quantity": 1, "avg_price": 100},
        )
        assert first.status_code == 200

        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "create_holding",
                "action": "create_holding",
                "message": "TIGER K방산&우주 보유종목을 등록했습니다.",
                "slots": {
                    "ticker": "449450",
                    "market": "KR",
                    "name": "TIGER K방산&우주",
                    "quantity": 426,
                    "avg_price": 49680,
                },
            },
        )

        response = client.post("/api/commands", json={"text": "TIGER K방산&우주 보유수량 426 현재주가 49680"})

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["id"] == first.json()["id"]
        assert body["result"]["ticker"] == "463250"
        holdings = client.get("/api/holdings").json()
        assert len(holdings) == 1
        assert holdings[0]["ticker"] == "463250"


def test_command_orchestrates_interest_area_create(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "executed",
                "intent": "create_interest_area",
                "action": "create_interest_area",
                "message": "AI 반도체 관심분야를 추가했습니다.",
                "slots": {
                    "name": "AI 반도체",
                    "category": "research",
                    "keywords": ["HBM", "온디바이스 AI"],
                    "linked_tickers": ["005930", "000660"],
                    "memo": "연결 종목 전망에 영향이 큰 연구성과만 알림",
                    "enabled": True,
                },
            },
        )

        response = client.post(
            "/api/commands",
            json={"text": "AI 반도체를 관심분야로 추가하고 키워드는 HBM, 온디바이스 AI, 연결 종목은 삼성전자와 SK하이닉스"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "executed"
        assert body["intent"] == "create_interest_area"
        assert body["result"]["name"] == "AI 반도체"
        assert body["result"]["linked_tickers"] == ["005930", "000660"]


def test_interest_label_command_requests_explicit_add(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        stub_plan(
            monkeypatch,
            {
                "status": "needs_confirmation",
                "intent": "create_interest",
                "action": "guide",
                "message": "관심종목 추가, 조회, 삭제 중 원하는 동작을 말해주세요.",
                "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자"},
            },
        )
        response = client.post("/api/commands", json={"text": "관심종목: 삼성전자"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "needs_confirmation"
        assert body["intent"] == "create_interest"
        assert "추가" in body["message"]

        interests = client.get("/api/interests").json()
        assert interests == []


def test_command_orchestrates_interest_list_and_delete(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        plans = iter(
            [
                {
                    "status": "executed",
                    "intent": "create_interest",
                    "action": "create_interest",
                    "message": "삼성전자 관심종목을 추가했습니다.",
                    "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자"},
                },
                {
                    "status": "executed",
                    "intent": "list_interest",
                    "action": "list_interest",
                    "message": "관심종목 현황입니다.",
                    "slots": {},
                },
                {
                    "status": "executed",
                    "intent": "delete_interest",
                    "action": "delete_interest",
                    "message": "삼성전자 관심종목을 삭제했습니다.",
                    "slots": {"ticker": "005930"},
                },
            ]
        )
        import backend.app.command_parser as command_parser
        monkeypatch.setattr(command_parser, "plan_command", lambda text: next(plans))

        client.post("/api/commands", json={"text": "삼성전자 관심종목 추가"})

        listed = client.post("/api/commands", json={"text": "관심종목 현황"})
        assert listed.status_code == 200
        assert listed.json()["intent"] == "list_interest"
        assert len(listed.json()["result"]["items"]) == 1

        deleted = client.post("/api/commands", json={"text": "삼성전자 관심종목 지워"})
        assert deleted.status_code == 200
        assert deleted.json()["intent"] == "delete_interest"


def test_known_expert_source_without_url_is_registered_disabled(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        before_sources = client.get("/api/expert-sources").json()
        stub_plan(
            monkeypatch,
            {
                "status": "needs_confirmation",
                "intent": "create_expert_source",
                "action": "guide",
                "message": "전문가 소스 등록에는 사용자가 확인한 공식 URL이 필요합니다.",
                "slots": {"name": "오건영"},
            },
        )
        response = client.post("/api/commands", json={"text": "오건영 SNS를 경제뉴스 참고소스로 추가"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "executed"
        assert body["result"]["name"] == "오건영 Facebook"
        assert body["result"]["url"] == "https://www.facebook.com/ohrang79"
        assert body["result"]["enabled"] is False

        sources = client.get("/api/expert-sources").json()
        assert len(sources) == len(before_sources)


def test_command_orchestrates_notification_analysis_and_guides(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        plans = iter(
            [
                {
                    "status": "executed",
                    "intent": "test_notification",
                    "action": "test_notification",
                    "message": "테스트 알림을 기록했습니다.",
                    "slots": {},
                },
                {
                    "status": "executed",
                    "intent": "run_analysis",
                    "action": "run_analysis",
                    "message": "삼성전자 분석을 실행했습니다.",
                    "slots": {"ticker": "005930", "market": "KR", "name": "삼성전자"},
                },
                {
                    "status": "needs_confirmation",
                    "intent": "create_schedule",
                    "action": "guide",
                    "message": "스케줄 등록에는 타입, 대상, 시간이 필요합니다.",
                    "slots": {"time": "08:00"},
                },
                {
                    "status": "unsupported",
                    "intent": "create_widget",
                    "action": "unsupported",
                    "message": "환율 위젯 기능은 아직 없습니다.",
                    "slots": {},
                },
            ]
        )
        import backend.app.command_parser as command_parser
        monkeypatch.setattr(command_parser, "plan_command", lambda text: next(plans))

        notification = client.post("/api/commands", json={"text": "테스트 알림 보내줘"})
        assert notification.status_code == 200
        assert notification.json()["intent"] == "test_notification"
        assert notification.json()["status"] == "executed"

        analysis = client.post("/api/commands", json={"text": "삼성전자 분석 실행"})
        assert analysis.status_code == 200
        assert analysis.json()["intent"] == "run_analysis"
        assert analysis.json()["status"] == "executed"

        schedule = client.post("/api/commands", json={"text": "매일 8시 뉴스 스케줄 추가"})
        assert schedule.status_code == 200
        assert schedule.json()["status"] == "needs_confirmation"
        assert schedule.json()["intent"] == "create_schedule"

        unsupported = client.post("/api/commands", json={"text": "환율 위젯 만들어줘"})
        assert unsupported.status_code == 200
        assert unsupported.json()["status"] == "unsupported"
        assert "아직 없습니다" in unsupported.json()["message"]


def test_analysis_and_notification_dry_runs(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        run = client.post("/api/analysis/run", json={"target": {"ticker": "TSLA"}})
        assert run.status_code == 200
        assert run.json()["status"] == "dry_run_completed"

        reports = client.get("/api/reports")
        assert reports.status_code == 200
        assert len(reports.json()) == 2

        notification = client.post("/api/notifications/test", json={})
        assert notification.status_code == 200
        assert notification.json()["channel"] == "dry-run"


def test_run_schedule_now_creates_report_or_notification(monkeypatch, tmp_path):
    import backend.app.services.schedule_runner as schedule_runner

    def fake_codex_analysis(run_type, target, context):
        from backend.app import db

        run = db.insert(
            "codex_run",
            {
                "run_type": run_type,
                "target": target,
                "agent_role": "schedule-analysis",
                "prompt_path": "",
                "output_path": "",
                "status": "completed",
                "started_at": db.utc_now(),
                "finished_at": db.utc_now(),
                "error": None,
            },
        )
        report = db.insert(
            "report",
            {
                "report_type": run_type,
                "target": target,
                "title": "fake codex report",
                "markdown": "# fake codex report",
                "codex_run_id": run["id"],
                "created_at": db.utc_now(),
            },
        )
        return {"run": run, "report": report}

    monkeypatch.setattr(schedule_runner, "run_codex_schedule_analysis", fake_codex_analysis)

    with make_client(monkeypatch, tmp_path) as client:
        schedules = client.get("/api/schedules").json()
        manual = next(item for item in schedules if item["schedule_type"] == "manual_codex_analysis")
        alert = next(item for item in schedules if item["schedule_type"] == "price_alert_watch")

        manual_result = client.post(f"/api/schedules/{manual['id']}/run")
        assert manual_result.status_code == 200
        assert manual_result.json()["status"] == "completed"
        assert manual_result.json()["report"]["report_type"] == "manual_codex_analysis"

        alert_result = client.post(f"/api/schedules/{alert['id']}/run")
        assert alert_result.status_code == 200
        assert alert_result.json()["notification"]["channel"] == "dry-run"
