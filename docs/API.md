# API 설계

## 1. 공통 원칙

- 모든 API는 `/api` prefix를 사용한다.
- 응답은 JSON을 기본으로 한다.
- 생성/수정 요청은 validation error를 명확히 반환한다.
- 애매한 자연어 명령은 실행하지 않고 확인 메시지를 반환한다.
- 현재 구현은 SQLite 기반 local v1 scaffold다. `DATABASE_URL=sqlite:///...` 형식을 지원한다.

### 진단

- `GET /api/health`
- `GET /api/diagnostics/codex`

`/api/diagnostics/codex`는 Docker/Oracle 배포에서 Codex CLI와 `/root/.codex/auth.json` mount가 인식되는지 확인한다. 호스트에서는 사용자가 `secrets/codex/auth.json`에 인증 파일을 직접 저장하고, Compose가 이 파일만 `/root/.codex/auth.json`으로 read-only mount한다. `/root/.codex` 디렉터리 자체는 Codex 상태 파일을 쓸 수 있도록 writable로 유지한다. 토큰 내용은 반환하지 않고 파일 존재 여부와 실행 파일 경로만 반환한다.

## 2. REST API

### 관심종목

- `POST /api/interests`
- `GET /api/interests`
- `PATCH /api/interests/{id}`
- `DELETE /api/interests/{id}`

`GET /api/interests` 응답에는 최신 `price_snapshot`이 있으면 `current_price`가 포함된다. 없으면 `null`이며 PWA는 `-`로 표시한다.

### 관심분야

- `POST /api/interest-areas`
- `GET /api/interest-areas`
- `PATCH /api/interest-areas/{id}`
- `DELETE /api/interest-areas/{id}`

관심분야는 종목 관심목록과 별도 category로 관리한다. 각 항목은 `name`, `category`, `keywords`, `linked_tickers`, `memo`, `enabled`를 가진다. 09:00 관심분야 연구성과 감지 스케줄은 활성 관심분야와 연결 종목을 context로 사용한다.

### 보유종목

- `POST /api/holdings`
- `GET /api/holdings`
- `PATCH /api/holdings/{id}`
- `DELETE /api/holdings/{id}`

`GET /api/holdings` 응답에는 최신 `price_snapshot`이 있으면 `current_price`가 포함된다. 같은 `ticker+market` 보유종목 등록은 기존 row를 업데이트한다.

### 스케줄

- `POST /api/schedules`
- `GET /api/schedules`
- `PATCH /api/schedules/{id}`
- `DELETE /api/schedules/{id}`
- `POST /api/schedules/{id}/run`

`POST /api/schedules/{id}/run`은 등록된 스케줄을 즉시 수동 실행한다. 가격 감시 스케줄은 KIS 현재가를 조회해 `price_snapshot`에 저장하고 알림 provider를 호출한다. 분석/뉴스 계열 스케줄은 현재 보유/관심종목과 갱신된 가격을 context로 만들어 `codex exec` 분석을 실행하고, Codex가 생성한 Markdown 리포트를 저장한다. Codex 실패 시에는 실패 사유가 포함된 fallback 리포트를 저장한다.
글로벌 경제뉴스 스케줄은 기본 RSS/search headline provider와 사용자가 추가한 RSS/feed 소스에서 `global_news.items`를 수집해 context에 포함한다. 리포트는 소스 확인 목록이 아니라 헤드라인 근거, 시장 영향, 보유/관심종목 영향, 투자 액션을 우선한다.

### 전문가 소스

- `POST /api/expert-sources`
- `GET /api/expert-sources`
- `PATCH /api/expert-sources/{id}`
- `DELETE /api/expert-sources/{id}`

### 자연어 명령

- `POST /api/commands`

명령 예시는 다음과 같다.

- 삼성전자 관심종목 추가
- 테슬라 3주 평균가 180달러로 보유종목 등록
- 보유종목: 삼성전자
- 삼성전자 160500원 284주 보유
- 여러 줄 포트폴리오 붙여넣기: `KODEX 200: 보유수량 613 / 현재주가 94050`
- 오건영 SNS를 경제뉴스 참고소스로 추가
- 오건영 Facebook 경제뉴스 소스 삭제

현재 v1 scaffold는 `/api/commands`를 Codex 기반 API orchestrator로 처리한다. 서버는 일반 자연어를 직접 파싱하지 않고, `api-orchestrator` skill과 JSON schema를 사용해 Codex가 만든 action plan을 실행한다. 관심분야, 관심종목, 보유종목, 전문가 소스 같은 자연어 명령은 모두 Codex orchestrator가 내부 format으로 구조화한다. 지원 기능이면 실행하고, 필수 값이 빠진 요청은 guide 성격의 `needs_confirmation`을 반환하며, 기능이 없으면 `unsupported`를 반환한다. `보유종목: 삼성전자`처럼 필수 값이 빠진 라벨형 명령은 보유종목 의도로 인식하되 수량/평균매수가 입력을 요청한다. `삼성전자 160500원 284주 보유`처럼 종목, 가격, 수량, 보유 의도가 모두 있는 문장은 보유종목 등록으로 실행한다. 같은 `ticker+market` 보유종목이 이미 있으면 새 row를 만들지 않고 기존 보유종목을 업데이트한다. 오건영 Facebook처럼 프로젝트가 후보 URL을 알고 있는 소스도 Codex가 action/slots를 만든 뒤 backend executor가 비활성 상태로 저장한다.
PWA는 경제뉴스 소스의 내부 필드(`category`, `platform`, `enabled`, `trust_note`)를 사용자 입력 폼으로 노출하지 않고 자연어 명령을 `/api/commands`로 보낸다.
여러 항목이 한 요청에 들어오면 Codex가 `batch` action의 `slots.items`로 개별 action을 만들고, backend가 순차 실행한다. 붙여넣은 포트폴리오에 평균매수가 없이 현재주가만 있으면 현재주가를 임시 평균단가로 저장한다. 같은 종목이 여러 계좌에 나뉘어 있으면 현재 DB 구조에서는 계좌별 row를 분리하지 않고 수량을 합산해 하나의 보유종목으로 저장한다.

### 분석

- `POST /api/analysis/run`
- `GET /api/analysis/runs/{id}`

현재 구현은 `dry_run_completed` 상태의 `codex_run`과 dry-run `report`를 생성한다. 실제 `codex exec` 호출은 provider 연결 단계에서 구현한다.

### 리포트

- `GET /api/reports`
- `GET /api/reports/{id}`

### 알림

- `POST /api/notifications/test`

`NOTIFICATION_MODE=dry-run`이면 알림을 `notification_log`에 기록만 한다. `NOTIFICATION_MODE=telegram`이면 Telegram Bot API로 실제 메시지를 보내고 성공/실패를 `notification_log`에 기록한다. FCM/SMTP 발송은 이후 provider 확장 단계에서 구현한다.

### 한국투자증권 Provider

- `GET /api/providers/kis/domestic-price/{ticker}`
- `GET /api/providers/kis/domestic-prices?tickers=005930,000660`

현재 구현은 `.env`의 `KIS_ENV`에 따라 실전/모의 base URL을 선택한다. 접근토큰은 메모리에 캐시해 만료 전까지 재사용하고, 토큰 오류가 발생하면 캐시를 무효화한 뒤 1회 재발급하여 요청을 재시도한다.
국내주식 멀티종목 현재가는 한국투자증권 `관심종목(멀티종목) 시세조회` API를 사용하며 1회 요청에 최대 30종목을 보낸다. 30종목을 넘기면 내부적으로 30개 단위로 나누어 호출한다.
응답에는 한국투자 원본 `output`과 앱에서 쓰기 쉬운 `items` 정규화 목록이 함께 포함된다.

## 3. 핵심 DB 엔티티

### `interest_stock`

- ticker
- market
- name
- tags
- memo
- enabled
- alert settings

### `interest_area`

- name
- category
- keywords
- linked_tickers
- memo
- enabled

### `holding_stock`

- ticker
- market
- name
- quantity
- avg_price
- buy_date
- target_price
- stop_loss_price
- memo
- enabled
- alert settings

### `expert_source`

- name
- category
- url
- platform
- enabled
- trust_note
- last_checked_at

### `codex_skill`

- name
- path
- purpose
- enabled
- version

### `codex_run`

- run_type
- target
- agent_role
- prompt_path
- output_path
- status
- started_at
- finished_at
- error

### 기타

- `schedule`
- `report`
- `notification_log`
- `price_snapshot`

## 4. 현재 구현 상태

- FastAPI app entrypoint: `backend.app.main:app`
- DB bootstrap: 앱 lifespan에서 SQLite table을 생성한다.
- 초기 seed: 기본 스케줄, 경제뉴스 소스, seed 리포트, 샘플 현재가 snapshot
- 구현된 CRUD: 관심종목, 관심분야, 보유종목, 스케줄, 전문가 소스
- 구현된 dry-run: 자연어 명령 일부, Codex 분석 실행 기록, 테스트 알림 기록
- 미구현 provider: 뉴스/공시/SNS 수집, 실제 Codex CLI, FCM, SMTP

## 5. 문서 현행화

- 공개 endpoint, request/response schema, 오류 정책이 바뀌면 이 문서를 갱신한다.
- 변경 배경은 `docs/HISTORY.md`에 기록한다.
- 구현 작업은 `docs/TODO.md`에서 추적한다.
- 구현 완료 후 `docs/CHANGELOG.md`에 기록한다.
