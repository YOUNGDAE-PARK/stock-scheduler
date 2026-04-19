# 아키텍처

## 1. 개요

`stock_scheduler`는 Python 백엔드와 React/Vite PWA를 하나의 프로젝트에서 관리한다.

- Backend: FastAPI
- Scheduler: APScheduler
- Local DB: SQLite
- Cloud DB: PostgreSQL 호환 `DATABASE_URL`
- Frontend: React/Vite PWA
- Notification: Firebase Cloud Messaging, SMTP email fallback
- Analysis: Codex CLI non-interactive execution

## 2. 주요 구성

### Backend API

FastAPI가 종목, 스케줄, 알림 이력, 리포트, 전문가 소스, 자연어 명령 API를 제공한다.

현재 entrypoint는 `backend.app.main:app`이며 앱 시작 시 SQLite table을 생성한다.

### Scheduler Worker

APScheduler가 `stock_report`, `price_alert_watch`, `global_news_digest`, `manual_codex_analysis` 타입 작업을 실행한다. API 서버와 같은 Python 프로젝트에 둔다.

현재는 scheduler heartbeat scaffold만 등록되어 있으며, 실제 도메인 job은 다음 단계에서 추가한다.

### Data Layer

초기 검증은 SQLite를 사용한다. 클라우드/VPS 이전 시 `DATABASE_URL` 교체로 PostgreSQL에 연결할 수 있게 ORM과 migration 구조를 설계한다.

### PWA

Galaxy S24 Chrome 설치를 기준으로 관심종목, 보유종목, 스케줄, 알림 이력, 분석 리포트, 경제뉴스 소스, Codex 분석 설정 화면을 제공한다.

현재 React/Vite PWA scaffold는 API 연결 상태, 자연어 명령 입력, 주요 목록 카운트, 테스트 알림 기록을 제공한다.

### Codex Pipeline

서버는 실행별 데이터 패키지를 생성하고 `/usr/bin/codex`의 `codex exec`를 비대화 모드로 호출한다. 출력은 JSON schema와 Markdown 최종 리포트로 저장한다.

## 3. 데이터 흐름

1. 사용자가 PWA 또는 자연어 명령으로 대상/스케줄을 등록한다.
2. FastAPI가 DB에 설정을 저장한다.
3. APScheduler가 정해진 시간에 데이터 수집과 규칙 기반 판단을 실행한다.
4. 필요한 경우 Codex CLI 분석을 실행한다.
5. 결과를 `report`, `notification_log`, `codex_run`, `price_snapshot` 등에 저장한다.
6. FCM 푸시를 우선 발송하고 실패 시 이메일 fallback과 UI 미전달 표시를 남긴다.

## 4. 배포 방식

### 로컬 검증

- Windows/WSL 환경에서 백엔드와 PWA를 실행한다.
- SQLite를 사용한다.
- FCM/SMTP는 dry-run provider와 실제 test provider를 단계적으로 검증한다.

### 안정 운영 전환

- 클라우드 또는 VPS로 이전한다.
- DB는 PostgreSQL로 이전한다.
- scheduler는 API 프로세스와 분리 실행할 수 있게 구조를 유지한다.

## 5. 문서 현행화

- 아키텍처, 배포 방식, 데이터 흐름이 바뀌면 이 문서를 갱신한다.
- 변경 배경은 `docs/HISTORY.md`에 기록한다.
- 실행 작업은 `docs/TODO.md`에 반영한다.
- 구현 완료 후 실제 변경은 `docs/CHANGELOG.md`에 기록한다.
