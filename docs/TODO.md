# TODO

이 문서는 현재 프로젝트의 구현 계획과 후속 작업을 추적한다.

상태 값:

- `Todo`
- `Doing`
- `Blocked`
- `Done`

우선순위:

- `P0`
- `P1`
- `P2`

## Now

- `[Done] [P0] 문서 구조 정비`
  - 관련: `PRD`, `ARCHITECTURE`, `API`, `SCHEDULER`, `CODEX_PIPELINE`, `CHANGELOG`, `TODO`
  - 완료 기준: 현재 구현과 문서가 서로 어긋나지 않음

- `[Done] [P0] 기본 도메인 CRUD와 스케줄 실행 구축`
  - 관련: 관심종목, 관심분야, 보유종목, 스케줄, 전문가 소스
  - 완료 기준: FastAPI CRUD와 PWA 화면이 정상 동작함

- `[Done] [P1] 뉴스 데이터 파이프라인 1차 구현`
  - 관련: `news_raw`, `news_refined`, `news_cluster`, `strategy_report`, `pipeline_state`
  - 완료 기준: 수집, 분류, 클러스터, 저장, purge가 모두 연결됨

- `[Done] [P1] 체인형 파이프라인과 재기동 복구`
  - 관련: `news_pipeline_chain`, `news_pipeline_resume`
  - 완료 기준: `news_collect -> news_classify -> market_cluster` 순차 실행과 재시작 복구가 동작함

- `[Done] [P1] source checkpoint 기반 incremental 수집`
  - 관련: `last_collected_at`, 최초 7일 backfill
  - 완료 기준: 최초는 7일 backfill, 이후는 source별 checkpoint 이후 기사만 유지함

- `[Done] [P1] 전략 리포트 2종 추가`
  - 관련: `interest_area_radar_report`, `interest_stock_radar_report`
  - 완료 기준: 두 리포트가 `report`와 `strategy_report`에 함께 저장됨

- `[Done] [P1] 파이프라인 테이블 화면 추가`
  - 관련: 프론트 `대시보드 / 파이프라인 테이블`, `백필 실행`
  - 완료 기준: `news_raw`, `news_refined`, `news_cluster`, `strategy_report`, `pipeline_state`를 UI에서 직접 볼 수 있음

## Next

- `[Todo] [P1] 시장 데이터 provider adapter 분리`
  - 관련: KIS, 향후 외부 provider
  - 완료 기준: mock/provider 경계가 명확하고 테스트에서 독립 검증 가능함

- `[Todo] [P1] 분류 SOP 고도화`
  - 관련: `importance`, `sentiment`, `user_links`
  - 완료 기준: 중요도/감성/유저 연결 규칙이 문서와 코드에서 더 일관되게 관리됨

- `[Todo] [P1] 파이프라인 테이블 필터/검색 추가`
  - 관련: 프론트 pipeline view
  - 완료 기준: source, ticker, 시간 기준으로 단계별 데이터 탐색이 쉬워짐

## Later

- `[Todo] [P2] PostgreSQL 이전 계획 구체화`
  - 관련: 배포/데이터 레이어
  - 완료 기준: SQLite에서 PostgreSQL로의 운영 전환 절차가 문서화됨

- `[Todo] [P2] 벡터/임베딩 기반 클러스터링 검토`
  - 관련: `news_cluster`
  - 완료 기준: 규칙 기반 1차 구현 이후 고도화 방향이 정리됨

- `[Todo] [P2] 유료 뉴스/본문 전문 수집 검토`
  - 관련: collector
  - 완료 기준: 헤드라인 기반 한계와 확장 방안이 정리됨

## 운영 규칙

- 완료된 항목은 삭제하지 않고 `Done`으로 유지한다.
- 공개 API, 스케줄, 데이터 구조가 바뀌면 관련 설계 문서를 함께 갱신한다.
- 의미 있는 동작 변경은 `docs/CHANGELOG.md`에 기록한다.
