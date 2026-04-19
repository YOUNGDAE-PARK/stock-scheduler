# TODO

`TODO.md`는 개발자와 Codex가 함께 보는 작업 추적의 단일 소스다. 외부 이슈 트래커가 생기기 전까지 모든 문서/설계/구현/검증 작업은 이 문서에서 추적한다.

## 항목 형식

- `[상태] [우선순위] 작업명`
  - 관련: 문서 또는 기능
  - 완료 기준: 완료를 판단할 수 있는 구체 조건

상태 값은 `Todo`, `Doing`, `Blocked`, `Done`을 사용한다. 우선순위는 `P0`, `P1`, `P2`를 사용한다.

## Now

- `[Done] [P0] 문서 골격 생성`
  - 관련: `PRD`, `ARCHITECTURE`, `API`, `SCHEDULER`, `CODEX_PIPELINE`, `CHANGELOG`, `TODO`, `HISTORY`
  - 완료 기준: `docs/` 아래 v1 문서 골격과 문서 관리 규칙이 생성됨

- `[Done] [P0] 관심종목/보유종목 데이터 모델 설계`
  - 관련: `docs/API.md`, `docs/ARCHITECTURE.md`
  - 완료 기준: 핵심 필드, validation, 관심/보유 중복 허용 정책이 DB schema 설계에 반영됨

- `[Done] [P0] FastAPI 기본 프로젝트 구조 설계`
  - 관련: Backend API
  - 완료 기준: 앱 entrypoint, 라우터 구조, 설정 로딩, DB session 구조가 정리됨

- `[Done] [P0] APScheduler 실행 로그 구조 설계`
  - 관련: `docs/SCHEDULER.md`
  - 완료 기준: 스케줄 실행, 실패, retry, 발송 상태, Codex 상태 기록 방식이 정리됨

- `[Done] [P0] 대시보드 표시 요구사항 구현`
  - 관련: Frontend PWA, Backend seed/current price
  - 완료 기준: 보유종목/관심종목 현재주가 표시, 기본 스케줄 상세 팝업, 분석 리포트/경제뉴스 소스 seed, 기능별 dry-run 테스트 버튼이 동작함

## Next

- `[Done] [P1] 자연어 명령 파서 v1 scaffold 구현`
  - 관련: `/api/commands`
  - 완료 기준: 관심종목/보유종목/전문가 소스/Codex 설정 등록, 삭제, 수정 명령과 애매한 명령 확인 흐름이 정의됨

- `[Todo] [P1] 실제 Codex CLI 분석 skill/pipeline 연결`
  - 관련: `docs/CODEX_PIPELINE.md`
  - 완료 기준: skill 경로, prompt 입력, output schema, timeout/failure 정책이 구현되고 dry-run runner를 대체할 수 있음

- `[Done] [P1] FCM/SMTP dry-run provider scaffold 구현`
  - 관련: Notifications/Email
  - 완료 기준: 실제 발송 전 payload 검증과 fallback 동작을 테스트할 수 있음

- `[Done] [P1] Galaxy S24 PWA 화면 구조 scaffold 구현`
  - 관련: Frontend PWA
  - 완료 기준: 관심종목, 보유종목, 스케줄, 알림 이력, 분석 리포트, 경제뉴스 소스, Codex 분석 설정 화면 구조가 정의됨

- `[Todo] [P1] 실제 스케줄 job 구현`
  - 관련: `stock_report`, `price_alert_watch`, `global_news_digest`, `manual_codex_analysis`
  - 완료 기준: APScheduler가 DB schedule을 읽어 각 job을 실행하고 실행 로그를 남김

- `[Todo] [P1] 시장 데이터 provider adapter 구현`
  - 관련: KIS, Alpha Vantage, Marketaux
  - 완료 기준: mock provider와 실제 provider 경계가 분리되고 테스트에서 mock으로 스케줄 실행을 검증함

## Later

- `[Todo] [P2] PostgreSQL 이전 계획 구체화`
  - 관련: Deployment/Data Layer
  - 완료 기준: SQLite에서 PostgreSQL로 이전하는 migration과 환경 변수 정책이 정리됨

- `[Todo] [P2] 증권사 계좌 자동 동기화 v2 후보 정리`
  - 관련: v2 Backlog
  - 완료 기준: v1 제외 범위를 유지하면서 v2 후보 요구사항이 별도 기록됨

## Done

- `[Done] [P0] TODO/HISTORY 문서 관리 체계 추가`
  - 관련: `docs/TODO.md`, `docs/HISTORY.md`, `docs/CHANGELOG.md`
  - 완료 기준: 작업 추적, 의사결정 이력, 구현 변경 기록의 역할이 분리됨

- `[Done] [P0] 실행 가능한 v1 scaffold 구현`
  - 관련: Backend, Frontend, Tests
  - 완료 기준: FastAPI 테스트와 Vite production build가 통과함

## 운영 규칙

- 새 요구사항이 들어오면 먼저 `docs/HISTORY.md`에 맥락을 기록한다.
- 실행 가능한 작업으로 쪼갤 수 있으면 이 문서에 추가한다.
- 완료된 항목은 삭제하지 않고 `Done`으로 이동한다.
- 공개 API, 스케줄, Codex pipeline, 데이터 구조가 바뀌면 관련 설계 문서를 함께 갱신한다.
- 구현 완료나 동작 변경이 있으면 `docs/CHANGELOG.md`에 기록한다.
