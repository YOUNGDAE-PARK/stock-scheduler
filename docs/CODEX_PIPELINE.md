# Codex Pipeline 설계

## 1. 목표

Codex CLI를 프로젝트 전용 분석 skill과 균형형 multi-agent 파이프라인으로 사용해 종목 리포트와 글로벌 경제뉴스 요약을 생성한다.

## 2. 기본 Skill

v1 기본 skill은 다음과 같다.

- `api-orchestrator`
- `macro-news-digest`
- `stock-technical-analysis`
- `stock-fundamental-news`
- `portfolio-risk-review`
- `final-investment-opinion`

`api-orchestrator`는 PWA의 `/api/commands` 자연어 입력을 API action JSON으로 변환한다. 사용자의 말을 기능 의도로 이해하고, 지원 기능이면 실행 가능한 action과 slots를 반환하며, 정보가 부족하면 guide, 기능이 없으면 unsupported로 답한다. skill 문서는 `codex_skills/api-orchestrator/SKILL.md`에 둔다.

스케줄 수동 실행은 스케줄 타입별 전용 skill을 사용한다.

- `stock_report`: `codex_skills/stock-report/SKILL.md`
- `global_news_digest`: `codex_skills/macro-news-digest/SKILL.md`
- `manual_codex_analysis`: `codex_skills/final-investment-opinion/SKILL.md`
- `interest_area_research_watch`: `codex_skills/interest-area-research-watch/SKILL.md`
- `price_alert_watch`: `codex_skills/price-alert-watch/SKILL.md`의 규칙형 알림 구조를 따른다.

## 3. 실행 방식

- 서버가 실행별 데이터 패키지를 생성한다.
- `/usr/bin/codex`의 `codex exec`를 비대화 모드로 호출한다.
- `codex exec --output-schema`로 결과 JSON schema를 강제한다.
- `codex exec --output-last-message`로 최종 Markdown 리포트를 저장한다.
- 실행 상태와 산출물 경로는 `codex_run`에 기록한다.

현재 구현은 `/api/commands`에서 `codex exec --output-schema`로 `api-orchestrator` skill을 실행해 action JSON을 만들고, 백엔드는 해당 action JSON을 API executor로 처리한다. 스케줄 리포트 실행은 스케줄 타입별 skill과 `schedule_analysis.schema.json`을 사용해 Codex Markdown 리포트를 생성한다. 글로벌 경제뉴스는 RSS/search headline provider가 만든 `global_news.items`를 context에 포함하고, skill은 소스 확인 목록이 아니라 투자 결론과 액션을 우선 작성한다. 관심분야 연구성과 감지는 `major_signal_detected`와 `notification_summary`를 함께 반환해 알림 여부를 결정한다.

## 4. Agent 구성

### 정기 종목 리포트

다음 agent를 병렬 실행한 뒤 최종 의견으로 합친다.

- macro/news agent
- stock agent
- risk/opinion agent

### 5분 급변 알림

- 우선 규칙 기반으로 판정한다.
- 큰 이벤트나 뉴스가 붙은 경우에만 가벼운 단일 Codex 요약을 붙인다.
- Codex 실패/timeout 시에도 기본 규칙 기반 알림과 원자료 링크는 발송한다.

## 5. 출력 원칙

종목 리포트는 다음 구조를 따른다.

- 결론: 매수/보유/매도
- 핵심 근거
- 반대 근거
- 리스크
- 확인할 뉴스/공시/SNS
- 다음 액션 기준

## 6. 실패 처리

- timeout과 non-zero exit를 실패로 기록한다.
- 실패한 Codex 실행은 재시도 정책에 따라 별도 처리한다.
- 알림 자체는 Codex 실패 때문에 차단하지 않는다.

## 7. 문서 현행화

- skill, agent 역할, prompt/output schema, 실패 처리 정책이 바뀌면 이 문서를 갱신한다.
- 변경 배경은 `docs/HISTORY.md`에 기록한다.
- 구현 작업은 `docs/TODO.md`에서 추적한다.
- 구현 완료 후 `docs/CHANGELOG.md`에 기록한다.
