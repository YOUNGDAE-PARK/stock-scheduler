# 스케줄러 설계

## 1. 사용자 스케줄 타입

현재 사용자에게 노출되는 `schedule_type`은 다음 5개다.

- `price_alert_watch`
- `manual_codex_analysis`
- `interest_area_research_watch`
- `interest_area_radar_report`
- `interest_stock_radar_report`

## 2. 사용자 스케줄 설명

### 5분 급변 알림

- 타입: `price_alert_watch`
- 주기: 5분
- 관심종목과 보유종목 가격 급변을 감시한다.
- KIS 현재가를 사용해 `price_snapshot`을 갱신한다.
- 같은 종목 알림에는 cooldown을 둔다.

### 수동 Codex 분석

- 타입: `manual_codex_analysis`
- 주기: 사용자가 원하는 시간 또는 수동 실행
- 선택 종목 또는 전체 컨텍스트를 바탕으로 일반 분석 리포트를 생성한다.

### 관심분야 연구성과 감지

- 타입: `interest_area_research_watch`
- 주기: 매일 09:00 KST
- 관심분야 키워드, 카테고리, linked ticker를 중심으로 의미 있는 연구/정책/기술 성과를 감시한다.

### 관심분야 Radar

- 타입: `interest_area_radar_report`
- 기본 seed 시간: 매일 07:30 KST
- 최근 정제 뉴스와 클러스터를 바탕으로 관심분야별 변화와 연결 종목 후보를 요약한다.

### 관심종목 Radar

- 타입: `interest_stock_radar_report`
- 기본 seed 시간: 매일 08:40 KST
- 관심종목과 직접 연관된 뉴스 이벤트, 단기 모멘텀, 감시 포인트를 요약한다.

## 3. 내부 파이프라인 job

### `news_pipeline_chain`

- 주기: 4시간 간격
- 실행 순서:
  1. `news_collect`
  2. `article_fetch`
  3. `news_classify`
  4. `market_cluster`

이 job은 독립적인 3개 interval job이 아니라 하나의 체인으로 실행된다.

### `news_pipeline_resume`

- 주기: 서버 재기동 직후 1회
- 역할:
  - `pipeline_state`를 읽고 직전 `running` 상태였던 단계부터 재개
  - 또는 미분류 `news_raw`, 최신 `news_refined`, 오래된 cluster 상태를 보고 필요한 단계부터 재실행

### `data_purge`

- 주기: 매일 03:15 KST
- 대상:
  - `news_raw`
  - `news_refined`
  - `news_cluster`
  - `strategy_report`
- 정책: 30일 초과 데이터 삭제

## 4. 수집 기간 정책

`news_collect`는 source별 checkpoint 기반 incremental 수집을 사용한다.

- 최초 실행:
  - source별 최근 7일을 backfill 대상으로 본다.
- 이후 실행:
  - source별 `last_collected_at`보다 새로운 기사만 유지한다.
- checkpoint 저장 위치:
  - `pipeline_state.meta.source_last_collected_at`

이 정책은 재기동 이후에도 그대로 이어진다.

`article_fetch`는 수집된 `news_raw` 중 `raw_body`가 비어 있는 기사에 대해 source URL 본문 추출을 시도한다. 본문 추출은 best-effort이며, 실패한 URL은 재시도 횟수 제한 안에서만 다시 시도한다.

## 5. 수동 실행 규칙

프론트의 `바로 실행` 또는 API `POST /api/schedules/{id}/run`은 다음처럼 동작한다.

- 가격 알림 스케줄:
  - 현재가 조회
  - 급변 판단
  - 알림 전송
- 일반 분석/관심분야 감지:
  - Codex skill 실행
  - fallback 리포트 가능
- 전략 리포트:
  - 파이프라인 데이터 상태 점검
  - 필요 시 `warm_strategy_pipeline()`으로 collector/classifier/cluster 보강
  - 최종 `report` 및 `strategy_report` 저장

## 6. 실행 로그와 상태

모든 실행은 가능한 한 DB에 상태를 남긴다.

- 시작/종료 시각
- 성공/실패
- 에러 메시지
- 알림 전송 여부
- Codex 실행 여부

파이프라인 단계는 특히 `pipeline_state`에 별도 기록한다.

- `running`
- `completed`
- `failed`

## 7. 프론트 연계

PWA에서는 다음 스케줄 관련 동작을 제공한다.

- 스케줄 카드 목록
- `schedule_type` 표시
- `바로 실행`
- `백필 실행`
- 파이프라인 테이블 조회

## 8. 문서 운영

- 스케줄 타입, 실행 주기, backfill 규칙, resume 규칙, purge 규칙이 바뀌면 이 문서를 갱신한다.
