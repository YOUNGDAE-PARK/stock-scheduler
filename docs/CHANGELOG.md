# CHANGELOG

## 2026-04-26

### Changed

- 스케줄 카드 목록에서 `schedule_type`과 실행 주기를 함께 보이도록 정리했다.
- 기존 독립 interval 설명 대신 뉴스 파이프라인을 체인 실행 구조로 정리했다.
- `global_news_digest`, `stock_report`, `holding_decision_report` 관련 잔여 타입과 문서 설명을 제거했다.

### Added

- `news_raw`, `news_refined`, `news_cluster`, `strategy_report`, `pipeline_state` 저장 계층을 추가했다.
- `news_pipeline_chain`, `news_pipeline_resume`, `data_purge` 내부 job을 추가했다.
- 전략 리포트 스케줄 `interest_area_radar_report`, `interest_stock_radar_report`를 추가했다.
- source별 `last_collected_at` checkpoint 기반 incremental 수집과 최초 7일 backfill 정책을 추가했다.
- `POST /api/pipeline/backfill`과 파이프라인 조회 API를 추가했다.
- 프론트에 `파이프라인 테이블` 화면과 `백필 실행` 버튼을 추가했다.
- `POST /api/reports/clear`와 프론트 `리포트 삭제` 버튼을 추가했다.
- `news_raw.raw_body` 컬럼과 `article_fetch` 단계를 추가했다.

### Notes

- 전략 리포트는 기존 `report`와 별도 `strategy_report`에 함께 저장한다.
- 파이프라인 단계는 서버 재시작 시 `pipeline_state`를 기준으로 중단 지점부터 재개한다.
- Classifier는 이제 `title + raw_summary + raw_body` 기준으로 분석한다.
- 2026-04-26: 최종 전략 리포트 컨텍스트를 `news_refined`/`news_cluster` 중심으로 정리하고, `raw_body`는 분류 입력으로 사용하며 `refined_summary`가 최종 관심종목 요약에 우선되도록 조정.
- 2026-04-26: 기본 글로벌 뉴스 소스를 Google News 검색형 feed에서 공식 RSS 중심 top10 큐레이션으로 교체하고, 기존 FRED/SEC/OpenDART/Naver 기본 소스를 제거. 오건영 Facebook은 유지.
- 2026-04-26: 백필 파이프라인에 실행 잠금 추가로 스케줄러/수동 실행 동시 충돌을 방지하고, 403으로 본문 확보가 불가능한 보조 query 뉴스 row는 startup 시 정리하도록 보강.
- 2026-04-26: 프론트의 `관심종목 테스트`, `보유종목 테스트`, `분석 테스트` 버튼을 제거하고 운영용 액션만 남겼다.
- 2026-04-26: API 기준 E2E 테스트를 추가해 `관심분야/관심종목 등록 -> backfill -> 정제/클러스터 -> Radar 스케줄 실행 -> report/strategy_report 생성` 흐름을 검증하도록 보강.
- 2026-04-26: Codex structured output schema를 최신 규칙에 맞게 수정해 실제 Radar 실행 실패를 해결하고, `backfill -> Radar -> notification` 운영용 E2E 버튼과 `/api/e2e/run` 엔드포인트를 추가.
