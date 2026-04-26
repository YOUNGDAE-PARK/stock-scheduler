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


def test_command_preflight_allows_configured_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://168.107.45.14:5173")
    with make_client(monkeypatch, tmp_path) as client:
        response = client.options(
            "/api/commands",
            headers={
                "Origin": "http://168.107.45.14:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://168.107.45.14:5173"


def test_interest_area_crud_and_seed_schedule(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        schedules = client.get("/api/schedules").json()
        research_watch = next(item for item in schedules if item["schedule_type"] == "interest_area_research_watch")
        assert research_watch["cron"] == "매일 09:00 KST"
        assert research_watch["target_type"] == "areas"
        assert all(item["schedule_type"] != "global_news_digest" for item in schedules)
        assert any(item["schedule_type"] == "interest_area_radar_report" for item in schedules)
        assert any(item["schedule_type"] == "interest_stock_radar_report" for item in schedules)
        assert all(item["schedule_type"] != "holding_decision_report" for item in schedules)

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


def test_pipeline_table_endpoints_and_backfill(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        import backend.app.main as main

        monkeypatch.setattr(
            main,
            "run_news_pipeline_chain",
            lambda force_collect=False: {
                "status": "completed",
                "collect": {"status": "completed", "inserted": 1},
                "classify": {"status": "completed", "inserted": 1},
                "cluster": {"status": "completed", "inserted": 1},
                "started_from": "news_collect",
            },
        )

        backfill = client.post("/api/pipeline/backfill")
        assert backfill.status_code == 200
        assert backfill.json()["status"] == "completed"

        raw = client.get("/api/pipeline/news-raw")
        refined = client.get("/api/pipeline/news-refined")
        cluster = client.get("/api/pipeline/news-cluster")
        strategy = client.get("/api/pipeline/strategy-reports")
        state = client.get("/api/pipeline/state")

        assert raw.status_code == 200
        assert refined.status_code == 200
        assert cluster.status_code == 200
        assert strategy.status_code == 200
        assert state.status_code == 200
        assert isinstance(raw.json(), list)
        assert isinstance(state.json(), list)


def test_clear_reports_endpoint(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        import backend.app.db as db

        db.insert(
            "report",
            {
                "report_type": "interest_area_radar",
                "target": {"scope": "test"},
                "title": "test report",
                "markdown": "body",
                "codex_run_id": None,
            },
        )
        db.insert(
            "strategy_report",
            {
                "report_type": "interest_stock_radar",
                "schedule_id": None,
                "title": "test strategy",
                "markdown": "body",
                "decision_json": {},
                "major_signal_detected": False,
                "notification_summary": None,
                "source_cluster_ids": [],
            },
        )

        response = client.post("/api/reports/clear")
        assert response.status_code == 200
        assert response.json() == {
            "deleted_reports": 1,
            "deleted_strategy_reports": 1,
        }
        assert client.get("/api/reports").json() == []
        assert client.get("/api/pipeline/strategy-reports").json() == []


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
        assert run.json()["status"] in {"completed", "dry_run_completed"}

        reports = client.get("/api/reports")
        assert reports.status_code == 200
        assert len(reports.json()) == 1

        notification = client.post("/api/notifications/test", json={})
        assert notification.status_code == 200
        assert notification.json()["channel"] == "dry-run"


def test_e2e_run_endpoint(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        import backend.app.main as main

        monkeypatch.setattr(
            main,
            "run_news_pipeline_chain",
            lambda force_collect=False: {
                "status": "completed",
                "collect": {"status": "completed", "inserted": 2},
                "fetch": {"status": "completed", "fetched": 2},
                "classify": {"status": "completed", "inserted": 2},
                "cluster": {"status": "completed", "inserted": 1},
            },
        )
        monkeypatch.setattr(
            main,
            "run_schedule_now",
            lambda schedule_id: {
                "status": "completed",
                "message": "개인화 전략 리포트를 생성했습니다.",
                "report": {"title": "E2E report"},
                "notification": {"channel": "dry-run"},
            },
        )

        response = client.post("/api/e2e/run?schedule_type=interest_area_radar_report")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["pipeline"]["collect"]["inserted"] == 2
        assert payload["result"]["notification"]["channel"] == "dry-run"


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


def test_strategy_pipeline_end_to_end(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path) as client:
        import backend.app.db as db
        import backend.app.services.news_pipeline as news_pipeline
        import backend.app.services.schedule_runner as schedule_runner

        interest_area = client.post(
            "/api/interest-areas",
            json={
                "name": "AI 반도체",
                "category": "research",
                "keywords": ["HBM", "온디바이스 AI"],
                "linked_tickers": ["005930"],
                "memo": "E2E test area",
            },
        )
        assert interest_area.status_code == 200

        interest_stock = client.post(
            "/api/interests",
            json={
                "ticker": "005930",
                "market": "KR",
                "name": "삼성전자",
                "tags": ["반도체"],
            },
        )
        assert interest_stock.status_code == 200

        holding = client.post(
            "/api/holdings",
            json={
                "ticker": "000660",
                "market": "KR",
                "name": "SK하이닉스",
                "quantity": 2,
                "avg_price": 150000,
            },
        )
        assert holding.status_code == 200

        monkeypatch.setattr(
            news_pipeline,
            "collect_global_news",
            lambda enabled_sources, stocks, interest_areas, max_items=36: {
                "items": [
                    {
                        "title": "삼성전자 HBM 공급 확대, AI 메모리 수요 강세",
                        "url": "https://example.com/news-1",
                        "source": "BBC Business",
                        "source_key": "default:bbc_business",
                        "category": "business",
                        "published_at": "2026-04-26T07:00:00+00:00",
                        "summary": "HBM 공급 확대와 AI 메모리 수요 강세가 이어진다.",
                    },
                    {
                        "title": "SK하이닉스와 반도체 업종, 온디바이스 AI 기대 확산",
                        "url": "https://example.com/news-2",
                        "source": "The Guardian Business",
                        "source_key": "default:guardian_business",
                        "category": "business",
                        "published_at": "2026-04-26T07:10:00+00:00",
                        "summary": "온디바이스 AI와 메모리 업황 기대가 높아진다.",
                    },
                ],
                "sources": [
                    {"feed_id": "default:bbc_business", "name": "BBC Business"},
                    {"feed_id": "default:guardian_business", "name": "The Guardian Business"},
                ],
                "errors": [],
            },
        )
        monkeypatch.setattr(
            news_pipeline,
            "fetch_article_body",
            lambda url: {
                "resolved_url": url,
                "source_url": url,
                "content_type": "text/html",
                "body": (
                    "삼성전자와 SK하이닉스가 HBM과 AI 메모리 수요 확대의 수혜를 본다. "
                    "관심분야인 AI 반도체와 온디바이스 AI 모멘텀이 강화되고 있다."
                ),
            },
        )
        monkeypatch.setattr(
            schedule_runner,
            "_refresh_current_prices",
            lambda stocks: {
                "updated": [
                    {**stock, "price": 165000 if stock["ticker"] == "005930" else 198000, "source": "test"}
                    for stock in stocks
                ],
                "failed": [],
            },
        )

        def fake_codex_analysis(run_type, target, context):
            refined_items = context.get("pipeline", {}).get("recent_refined_news") or []
            assert refined_items, "final analysis should receive refined news context"
            assert refined_items[0].get("refined_summary"), "refined summary should be populated"

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
                    "title": "관심종목 Radar E2E",
                    "markdown": "# 관심종목 Radar\n\n- refined summary 기반 E2E 리포트",
                    "codex_run_id": run["id"],
                    "created_at": db.utc_now(),
                },
            )
            return {
                "run": run,
                "report": report,
                "analysis": {
                    "title": report["title"],
                    "markdown": report["markdown"],
                    "major_signal_detected": True,
                    "notification_summary": "삼성전자 HBM 모멘텀",
                    "decision_json": {
                        "refined_titles": [item.get("title") for item in refined_items],
                        "used_refined_summary": refined_items[0].get("refined_summary"),
                    },
                },
            }

        monkeypatch.setattr(schedule_runner, "run_codex_schedule_analysis", fake_codex_analysis)

        backfill = client.post("/api/pipeline/backfill")
        assert backfill.status_code == 200
        assert backfill.json()["status"] == "completed"
        assert backfill.json()["collect"]["inserted"] == 2
        assert backfill.json()["fetch"]["fetched"] == 2
        assert backfill.json()["classify"]["inserted"] == 2
        assert backfill.json()["cluster"]["inserted"] >= 1

        raw_rows = client.get("/api/pipeline/news-raw").json()
        refined_rows = client.get("/api/pipeline/news-refined").json()
        cluster_rows = client.get("/api/pipeline/news-cluster").json()
        assert len(raw_rows) == 2
        assert all(row["raw_body"] for row in raw_rows)
        assert len(refined_rows) == 2
        assert any("005930" in row["tickers"] for row in refined_rows)
        assert any(row["user_links"]["interest_areas"] for row in refined_rows)
        assert len(cluster_rows) >= 1

        schedules = client.get("/api/schedules").json()
        radar = next(item for item in schedules if item["schedule_type"] == "interest_stock_radar_report")
        run_result = client.post(f"/api/schedules/{radar['id']}/run")
        assert run_result.status_code == 200

        payload = run_result.json()
        assert payload["status"] == "completed"
        assert payload["report"]["report_type"] == "interest_stock_radar_report"
        assert payload["strategy_report"]["report_type"] == "interest_stock_radar"
        assert payload["run"]["status"] == "completed"
        assert payload["report"]["title"] == "관심종목 Radar E2E"

        reports = client.get("/api/reports").json()
        strategy_reports = client.get("/api/pipeline/strategy-reports").json()
        pipeline_state = client.get("/api/pipeline/state").json()

        assert any(report["title"] == "관심종목 Radar E2E" for report in reports)
        assert any(report["report_type"] == "interest_stock_radar" for report in strategy_reports)
        assert {row["pipeline_name"] for row in pipeline_state} >= {
            "news_collect",
            "article_fetch",
            "news_classify",
            "market_cluster",
        }
