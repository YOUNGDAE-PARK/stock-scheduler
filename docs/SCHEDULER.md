# 스케줄러 설계

## 1. 스케줄 타입

스케줄 타입은 v1에서 다음 다섯 가지로 고정한다.

- `stock_report`
- `price_alert_watch`
- `global_news_digest`
- `manual_codex_analysis`
- `interest_area_research_watch`

## 2. 스케줄 대상

스케줄 대상은 다음 중 하나다.

- `interest`
- `holding`
- `all`
- 특정 ticker 목록
- `areas`

## 3. 주요 스케줄

### 5분 급변 알림

- 장중 5분마다 관심종목과 보유종목 가격을 확인한다.
- 기본 알림 기준:
  - 5분 수익률 절대값 `>= 1.5%`
  - 최근 20개 5분 수익률 대비 `z-score >= 2.0`
  - 거래량 데이터가 있으면 최근 평균 대비 `2배 이상`
- 보유종목은 목표가/손절가 근접, 평균매수가 돌파/이탈, 당일 손익 급변도 감지한다.
- 같은 종목은 30분 cooldown을 둔다.

### 글로벌 경제뉴스 08:00

- 매일 08:00 KST 실행한다.
- 미국장 마감, 야간 글로벌 뉴스, 환율/금리/원자재, 한국장 영향을 요약한다.
- RSS/search headline provider로 실제 헤드라인 후보를 수집하고, 금리/환율/원자재/섹터/보유·관심종목 영향과 투자 액션을 우선 도출한다.

### 글로벌 경제뉴스 18:00

- 매일 18:00 KST 실행한다.
- 한국장 마감, 유럽/미국 개장 전 이슈, 당일 주요 공시/섹터 이슈를 요약한다.
- 단순 소스 확인 목록이 아니라 수집된 헤드라인 흐름을 근거로 `추가/보유/축소/대기` 관점의 결론을 낸다.

### 관심분야 연구성과 09:00

- 매일 09:00 KST 실행한다.
- 활성 관심분야의 keyword, category, linked ticker를 context로 사용한다.
- 연구/제품/임상/특허/정책/상용화 성과가 연결 종목의 주식 전망에 의미 있게 이어질 때만 주요 성과로 판정한다.
- 주요 성과가 감지되면 리포트 본문과 함께 Telegram 알림을 보낸다.

## 4. 실행 로그

모든 실행은 다음 상태를 DB에 남긴다.

- 실행 시작/종료 시각
- 성공/실패 상태
- 실패 error
- 푸시 발송 상태
- 메일 발송 상태
- Codex 실행 상태

현재 구현은 APScheduler `BackgroundScheduler`를 FastAPI lifespan에서 시작하고, 30분 간격 heartbeat job을 dry-run `notification_log`에 기록한다. `매일 HH:MM KST` 형식의 활성 스케줄은 앱 시작 시 cron job으로 등록한다.

PWA의 스케줄 `바로 실행`은 `POST /api/schedules/{id}/run`을 호출한다. 가격 감시 스케줄은 KIS 현재가를 조회하고 Telegram 알림을 보낸다. 리포트형 스케줄은 스케줄 타입별 Codex skill로 Markdown 리포트를 생성하고, 생성 결과와 리포트 본문 전체를 Telegram으로 알린다. Telegram 길이 제한을 넘는 리포트는 여러 메시지로 나누어 보낸다. Codex 실패 시에도 fallback 리포트를 만들고 실패 알림과 본문을 보낸다. 관심분야 연구성과 스케줄은 주요 성과 감지 또는 분석 실패/fallback 때 알림을 보낸다.

## 5. Retry/Fallback

- FCM 푸시는 재시도한다.
- 푸시 실패 또는 미전달 상태는 이메일 fallback으로 보강한다.
- Codex 실패 또는 timeout 시에도 규칙 기반 알림과 원자료 링크는 발송한다.
- 실패는 UI에서 확인 가능한 미전달/실패 상태로 남긴다.

## 6. 문서 현행화

- 스케줄 타입, 실행 주기, retry/fallback, 알림 보장 정책이 바뀌면 이 문서를 갱신한다.
- 변경 배경은 `docs/HISTORY.md`에 기록한다.
- 구현 작업은 `docs/TODO.md`에서 추적한다.
- 구현 완료 후 `docs/CHANGELOG.md`에 기록한다.
