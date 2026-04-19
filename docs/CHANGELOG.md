# Changelog

모든 중요한 구현 변경과 릴리즈 관점 변경을 이 문서에 기록한다. 요구사항과 의사결정의 배경은 `docs/HISTORY.md`에 기록하고, 앞으로 할 일은 `docs/TODO.md`에서 추적한다.

## 2026-04-18

### Added

- v1 문서 골격을 추가했다.
- `docs/PRD.md`를 추가해 제품 목표, 사용자 시나리오, 기능 범위, 성공 기준을 정리했다.
- `docs/ARCHITECTURE.md`를 추가해 시스템 구성, 데이터 흐름, 배포 구조를 정리했다.
- `docs/API.md`를 추가해 REST API와 핵심 DB 엔티티를 정리했다.
- `docs/SCHEDULER.md`를 추가해 스케줄 타입, 실행 주기, retry/fallback, 알림 보장 정책을 정리했다.
- `docs/CODEX_PIPELINE.md`를 추가해 Codex skill, agent 구성, 실행 방식, 실패 처리를 정리했다.
- `docs/TODO.md`를 추가해 작업 추적의 단일 소스를 만들었다.
- `docs/HISTORY.md`를 추가해 요구사항과 의사결정 이력의 단일 소스를 만들었다.

### Documentation

- 새 요구사항 처리 순서를 문서화했다.
- `TODO.md`, `HISTORY.md`, `CHANGELOG.md`의 역할을 분리했다.
- 문서 현행화 검사 기준을 초기 문서에 반영했다.

### Implemented

- FastAPI backend scaffold를 추가했다.
- SQLite table bootstrap과 관심종목, 보유종목, 스케줄, 전문가 소스 CRUD API를 추가했다.
- 자연어 명령 API의 v1 scaffold를 추가했다.
- Codex 분석 dry-run runner와 report 생성 흐름을 추가했다.
- 테스트 알림 dry-run provider와 `notification_log` 기록을 추가했다.
- APScheduler heartbeat scaffold를 추가했다.
- React/Vite PWA scaffold를 추가했다.
- backend API 테스트를 추가했다.

### Fixed

- `보유종목: 삼성전자` 같은 라벨형 명령이 미지원으로 처리되던 문제를 수정했다.
- 라벨형 관심종목/보유종목 명령은 즉시 DB를 변경하지 않고 확인 또는 추가 정보 요청을 반환한다.

### Changed

- `/api/commands` 자연어 처리를 API orchestrator 방향으로 확장했다.
- 관심종목/보유종목 목록, 추가, 삭제와 테스트 알림, dry-run 분석 실행을 자연어에서 처리한다.
- 지원 기능의 정보 부족은 `needs_confirmation`, 미지원 기능은 `unsupported`로 구분한다.
- `삼성전자 160500원 284주 보유`처럼 자연스러운 보유 표현을 보유종목 등록으로 처리한다.
- 문자열 parser 기반 자연어 해석을 제거하고, Codex `api-orchestrator` skill이 JSON action plan을 만들며 백엔드는 action executor 역할만 하도록 변경했다.
- 같은 `ticker+market` 보유종목 등록 요청은 중복 insert 대신 기존 row update로 처리한다.

### Added

- 보유종목/관심종목 카드에 현재주가와 수량 정보를 표시한다.
- 기본 스케줄, 분석 리포트, 경제뉴스 소스 seed 데이터를 추가한다.
- 스케줄 없이 기능별 dry-run 테스트를 실행하는 PWA 버튼을 추가한다.
- 스케줄 항목 클릭 시 상세 팝업을 표시한다.
- 관심종목/보유종목 API 응답에 최신 `price_snapshot` 기반 `current_price`를 포함한다.
- `.env` 기반 한국투자증권 실전/모의 Open API 설정과 `.env.example` 템플릿을 추가했다.
- 한국투자증권 접근토큰을 만료 전까지 재사용하고, 토큰 오류 시 1회 재발급 후 API 요청을 재시도하는 KIS client를 추가했다.
- 한국투자증권 `관심종목(멀티종목) 시세조회` 기반 국내주식 멀티 현재가 조회 API를 추가했다.
- 분석 리포트 선택 시 전체 화면 Markdown 상세 모달로 읽을 수 있게 했다.
- `NOTIFICATION_MODE=telegram`일 때 테스트 알림과 자연어 알림 명령이 실제 Telegram 메시지를 보내도록 했다.
- 프론트/백엔드 개발 서버를 함께 실행하는 `scripts/start-dev.sh`를 추가했다.
- 스케줄 항목을 수동으로 바로 실행하는 API와 PWA 버튼을 추가했다.
- 수동 스케줄 실행을 dry-run 대신 KIS 현재가 갱신, Telegram 알림, 실제 데이터 기반 리포트 생성 흐름으로 변경했다.
- 분석/뉴스 스케줄 수동 실행이 `codex exec`로 Markdown 리포트를 생성하도록 연결했다.
- tickers가 비어 있는 수동 분석 스케줄은 보유/관심종목 전체를 분석 대상으로 사용하고, Codex 실패 메시지를 요약해 저장하도록 개선했다.
- 스케줄 타입별 Codex skill을 추가하고, 스케줄 리포트 생성 결과도 Telegram 알림으로 발송하도록 했다.
- Telegram 리포트 알림에 Markdown 본문 전문을 포함하고, 길면 여러 메시지로 분할 전송하도록 했다.
- Docker Compose 기반 PostgreSQL/backend/frontend 실행 구성을 추가하고, WSL 네트워크 우회용 override 파일을 분리했다.
- 경제뉴스 소스를 PWA에서 추가/삭제할 수 있게 하고, 오건영 Facebook seed를 비활성 상태로 추가했다.
- 자연어 명령에서 오건영 Facebook 후보 소스를 URL 없이 요청해도 비활성 상태로 등록하거나 기존 항목을 반환하도록 개선했다.
- 관심분야 CRUD API와 PWA 카드를 추가하고, 09:00 관심분야 연구성과 감지 스케줄과 전용 Codex skill을 추가했다.
- 글로벌 경제뉴스 스케줄에 RSS/search headline 수집 provider를 추가하고, macro-news skill을 투자 결론과 액션 중심으로 강화했다.
- Docker backend 이미지에 Codex CLI 설치를 추가하고, 사용자가 직접 저장하는 `secrets/codex/auth.json`을 read-only로 mount하도록 했다.
- Codex 컨테이너가 상태 파일을 쓸 수 있도록 `auth.json` 파일만 read-only mount하고 `/root/.codex` 디렉터리는 writable로 유지하도록 수정했다.
- 관심분야 자연어 action을 Codex orchestrator schema와 executor에 추가하고, `/api/commands`의 패턴 우회 처리를 제거했다.
- WSL Docker override에서 backend를 host network로 실행해 Codex CLI의 외부 HTTPS 연결 timeout을 우회하도록 했다.
- Codex orchestrator가 optional boolean slot을 `null`로 반환해도 DB 기본값으로 저장되도록 처리했다.
- 경제뉴스 소스 입력 폼에서 내부 필드를 제거하고, 추가/삭제를 자연어 명령 중심으로 처리하도록 변경했다.
- 자연어 명령에 경제뉴스 소스 삭제 action을 추가했다.
- 자연어 명령에 `batch` action을 추가해 여러 보유종목을 한 번에 등록할 수 있게 했다.
- 일괄 보유종목 등록 시 같은 `ticker+market` 항목은 수량을 합산해 저장하도록 했다.
- 주요 보유 ETF/종목명은 backend 정규화 사전으로 ticker를 보정하고, 기존 row의 잘못된 ticker도 같은 이름 기준으로 업데이트하도록 했다.
- GitHub Actions CI workflow와 Oracle Cloud 수동 배포 workflow를 추가했다.
- Oracle VM Docker bootstrap/deploy 스크립트와 CI/CD 문서를 추가했다.
- 1GB Oracle 무료 VM용 SQLite 기반 lite compose와 SQLite 백업 스크립트를 추가했다.
