# API 설계

## 1. 공통 원칙

- 모든 API는 `/api` prefix를 사용한다.
- 응답은 JSON이다.
- 생성/수정 요청은 validation error를 명확히 반환한다.
- 자연어 명령은 서버가 직접 파싱하지 않고 Codex 오케스트레이터를 통해 action plan으로 변환한다.

## 2. 기본 엔드포인트

### 진단

- `GET /api/health`
- `GET /api/diagnostics/codex`

### 관심종목

- `POST /api/interests`
- `GET /api/interests`
- `PATCH /api/interests/{id}`
- `DELETE /api/interests/{id}`

`GET /api/interests`는 최신 `price_snapshot`이 있으면 `current_price`를 함께 반환한다.

### 관심분야

- `POST /api/interest-areas`
- `GET /api/interest-areas`
- `PATCH /api/interest-areas/{id}`
- `DELETE /api/interest-areas/{id}`

관심분야는 `name`, `category`, `keywords`, `linked_tickers`, `memo`, `enabled`를 가진다.

### 보유종목

- `POST /api/holdings`
- `GET /api/holdings`
- `PATCH /api/holdings/{id}`
- `DELETE /api/holdings/{id}`

`GET /api/holdings`도 최신 `price_snapshot` 기반 `current_price`를 포함한다.

### 스케줄

- `POST /api/schedules`
- `GET /api/schedules`
- `PATCH /api/schedules/{id}`
- `DELETE /api/schedules/{id}`
- `POST /api/schedules/{id}/run`

현재 유효한 `schedule_type`:

- `price_alert_watch`
- `manual_codex_analysis`
- `interest_area_research_watch`
- `interest_area_radar_report`
- `interest_stock_radar_report`

전략 리포트 스케줄 `interest_area_radar_report`, `interest_stock_radar_report`는 즉석 수집보다 내부 파이프라인 산출물 `news_raw`, `news_refined`, `news_cluster`를 우선 사용한다. 다만 데이터가 비어 있거나 오래되면 필요한 수집/분류/클러스터 단계를 먼저 보강한 뒤 리포트를 만든다.

### 전문가 소스

- `POST /api/expert-sources`
- `GET /api/expert-sources`
- `PATCH /api/expert-sources/{id}`
- `DELETE /api/expert-sources/{id}`

### 자연어 명령

- `POST /api/commands`

Codex orchestrator가 action plan을 만들고 backend executor가 이를 실행한다.

### 분석

- `POST /api/analysis/run`
- `GET /api/analysis/runs/{id}`

### 리포트

- `GET /api/reports`
- `GET /api/reports/{id}`
- `POST /api/reports/clear`

### 알림

- `POST /api/notifications/test`

### KIS 시세

- `GET /api/providers/kis/domestic-price/{ticker}`
- `GET /api/providers/kis/domestic-prices?tickers=005930,000660`

## 3. 파이프라인 API

- `POST /api/pipeline/backfill`
- `GET /api/pipeline/news-raw`
- `GET /api/pipeline/news-refined`
- `GET /api/pipeline/news-cluster`
- `GET /api/pipeline/strategy-reports`
- `GET /api/pipeline/state`

### `POST /api/pipeline/backfill`

강제로 뉴스 파이프라인 체인을 한 번 실행한다.

- 순서: `news_collect -> news_classify -> market_cluster`
- 최초 수집 정책: source별 최근 7일 backfill
- 이후 수집 정책: source별 `last_collected_at` 이후 기사만 유지
- 결과: 삽입/건너뜀/필터링 카운트와 pipeline state 반영

이 엔드포인트는 프론트의 `백필 실행` 버튼과 연결된다.

### `POST /api/reports/clear`

기존 `report`와 `strategy_report`의 과거 데이터를 모두 삭제한다.

- 삭제 대상:
  - `report`
  - `strategy_report`
- 용도:
  - 테스트/seed 리포트 정리
  - 파이프라인을 깨끗한 상태로 다시 확인할 때 사용

### 파이프라인 조회 API

프론트의 파이프라인 테이블 화면에서 단계별 데이터를 직접 검증하기 위한 API다.

- `news-raw`: 원본 headline/메타
- `news-refined`: 분류/태깅 결과
- `news-cluster`: 내러티브 묶음 결과
- `strategy-reports`: 최종 개인화 리포트 원본
- `state`: 단계 상태와 source checkpoint

## 4. 주요 저장 모델

### `news_raw`

- `title`
- `url`
- `source`
- `category`
- `published_at`
- `collected_at`
- `raw_summary`
- `raw_body`
- `content_hash`
- `raw_payload`

### `news_refined`

- `news_raw_id`
- `tickers`
- `sectors`
- `importance`
- `sentiment`
- `user_links`
- `refined_summary`
- `classified_at`

### `news_cluster`

- `cluster_key`
- `theme`
- `narrative`
- `related_news_ids`
- `tickers`
- `sectors`
- `importance_score`
- `cluster_window_start`
- `cluster_window_end`

### `strategy_report`

- `report_type`
- `schedule_id`
- `title`
- `markdown`
- `decision_json`
- `major_signal_detected`
- `notification_summary`
- `source_cluster_ids`

### `pipeline_state`

- `pipeline_key`
- `status`
- `started_at`
- `finished_at`
- `error`
- `meta`

`meta`에는 source별 `last_collected_at` checkpoint 같은 운영 메타데이터가 들어간다.

## 5. 현재 리포트 타입

- `interest_area_radar`
- `interest_stock_radar`

기존 `report` 테이블 조회 흐름은 유지하며, 전략 리포트 원본은 `strategy_report`에도 별도로 저장한다.

## 6. 문서 운영

- 공개 API, request/response, 스케줄 타입, 파이프라인 저장 모델이 바뀌면 이 문서를 갱신한다.
