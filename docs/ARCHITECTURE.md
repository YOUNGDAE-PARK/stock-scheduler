# 아키텍처

## 1. 개요

`stock_scheduler`는 FastAPI 백엔드, APScheduler 워커, SQLite/PostgreSQL 데이터 저장소, React/Vite PWA 프론트엔드로 구성된다.

- Backend: FastAPI
- Scheduler: APScheduler
- Local DB: SQLite
- Deploy DB: PostgreSQL
- Frontend: React/Vite PWA
- Notification: Telegram 우선, 기타 fallback 확장 가능
- Analysis: Codex CLI 또는 Gemini 기반 오케스트레이션

## 2. 주요 구성

### Backend API

FastAPI가 관심종목, 관심분야, 보유종목, 스케줄, 전문가 소스, 리포트, 파이프라인 조회 API를 제공한다.

실제 엔트리포인트는 `backend.app.main:app`이다.

### Scheduler Worker

APScheduler는 사용자 스케줄과 내부 파이프라인 job을 함께 관리한다.

사용자 visible 스케줄 타입:

- `price_alert_watch`
- `manual_codex_analysis`
- `interest_area_research_watch`
- `interest_area_radar_report`
- `interest_stock_radar_report`

내부 파이프라인 job:

- `news_pipeline_chain`
- `news_pipeline_resume`
- `data_purge`

`news_pipeline_chain`은 4시간 간격으로 `news_collect -> news_classify -> market_cluster`를 순차 실행한다. `news_pipeline_resume`은 서버 재기동 직후 1회 실행되어 `pipeline_state`를 보고 멈춘 단계부터 이어서 수행한다.

### Data Layer

기본 저장소는 SQLite이며 `DATABASE_URL`을 통해 PostgreSQL로 전환 가능하다.

핵심 도메인 테이블:

- `interest_stock`
- `interest_area`
- `holding_stock`
- `schedule`
- `report`
- `notification_log`
- `codex_run`
- `price_snapshot`

뉴스 파이프라인 전용 테이블:

- `news_raw`
- `news_refined`
- `news_cluster`
- `strategy_report`
- `pipeline_state`

`pipeline_state`는 단계별 `running/completed/failed` 상태와 source별 `last_collected_at` checkpoint를 저장해 재기동 복구와 incremental 수집에 사용한다.

### Frontend PWA

PWA는 두 개의 상위 뷰를 제공한다.

- 대시보드
- 파이프라인 테이블

대시보드는 기존 카드형 관리 화면이며, 파이프라인 테이블은 다음 저장 데이터를 직접 보여준다.

- `news_raw`
- `news_refined`
- `news_cluster`
- `strategy_report`
- `pipeline_state`

또한 프론트에서 `백필 실행` 버튼으로 `POST /api/pipeline/backfill`을 호출할 수 있다.

### Codex Pipeline

최종 전략 리포트는 “즉석 단일 실행”보다 “수집-정제-클러스터-리포트” 구조를 우선한다.

1. Collector가 RSS/search/feed를 읽고 `news_raw`에 저장
2. Article Fetcher가 source URL에서 본문을 가져와 `news_raw.raw_body`를 채움
3. Classifier가 `title + raw_summary + raw_body`를 분석해 `news_refined`에 저장
4. Market Reporter가 관련 뉴스를 내러티브로 묶어 `news_cluster`에 저장
5. Personal Strategy Reporter가 최종 `interest_area_radar`, `interest_stock_radar` 리포트를 생성

## 3. 데이터 흐름

1. 사용자가 PWA 또는 자연어 명령으로 도메인 데이터를 등록한다.
2. FastAPI가 검증 후 DB에 저장한다.
3. APScheduler가 4시간마다 뉴스 파이프라인 체인을 실행한다.
4. Collector는 최초 실행 시 최근 7일을 backfill하고, 이후에는 source별 `last_collected_at` 이후 기사만 유지한다.
5. Article Fetcher는 본문이 비어 있는 `news_raw`에 대해 source URL 본문 추출을 시도한다.
6. Classifier는 `title + raw_summary + raw_body` 기준으로 미분류 `news_raw`를 `news_refined`로 변환한다.
7. Market Reporter는 최근 `news_refined`를 `news_cluster`로 묶는다.
8. 사용자 스케줄 실행 시 최종 전략 리포트는 `news_cluster`와 사용자 컨텍스트를 사용해 생성된다.
9. 결과는 기존 `report`와 별도 `strategy_report`에 함께 저장된다.
10. Telegram 알림 또는 로그가 남는다.

## 4. 운영 규칙

- 시간 필드는 ISO 8601 문자열로 저장한다.
- 파이프라인 데이터는 30일 보관 후 purge한다.
- 파이프라인 단계는 idempotent하게 설계한다.
- 리포트 실행 전 파이프라인 데이터가 비어 있거나 오래되면 `warm_strategy_pipeline()`으로 필요한 단계만 보강한다.

## 5. 배포

### 로컬 개발

- WSL/로컬에서 FastAPI + Vite를 직접 실행
- SQLite 사용

### Docker Compose

- backend + frontend + PostgreSQL
- 컨테이너 재빌드 시 프론트 변경 사항 반영:
  - `docker compose up -d --build`

## 6. 문서 운영

- 구조가 바뀌면 이 문서를 먼저 갱신한다.
- 스케줄 규칙은 `docs/SCHEDULER.md`에서 상세 관리한다.
- Codex/뉴스 처리 규칙은 `docs/CODEX_PIPELINE.md`에서 상세 관리한다.
