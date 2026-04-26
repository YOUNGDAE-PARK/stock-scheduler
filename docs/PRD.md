# 주식 현황/분석/알림 자동화 시스템 PRD

## 1. 제품 목표

`stock_scheduler`는 국내/미국 주식의 관심종목, 관심분야, 보유종목을 분리 관리하고 정기 리포트와 알림을 PWA에서 확인할 수 있게 하는 개인 투자 보조 시스템이다.

v1의 목표는 자동매매가 아니라 다음 세 가지다.

- 데이터 수집 자동화
- 투자 판단 보조용 분석 리포트 생성
- 가격 급변 및 의미 있는 뉴스 변화에 대한 알림

## 2. 핵심 사용자 시나리오

- 사용자는 관심종목을 등록하고 진입 후보를 관찰한다.
- 사용자는 관심분야를 등록하고 산업, 정책, 기술, 공급망 변화 흐름을 감시한다.
- 사용자는 보유종목의 수량, 평단, 메모를 관리하고 실시간 가격과 함께 본다.
- 사용자는 자연어 명령으로 종목, 관심분야, 소스, 스케줄을 빠르게 등록한다.
- 사용자는 스케줄 카드 또는 수동 실행으로 Codex 기반 분석 리포트를 생성한다.
- 사용자는 파이프라인 테이블 화면에서 수집된 뉴스가 `news_raw -> news_refined -> news_cluster`로 어떻게 정제되는지 직접 확인한다.

## 3. 기능 범위

### v1 포함

- 관심종목 CRUD
- 관심분야 CRUD
- 보유종목 CRUD
- 스케줄 CRUD 및 수동 실행
- 알림 이력 조회
- 분석 리포트 조회
- 전문가/RSS 소스 관리
- 자연어 명령 `/api/commands`
- 5분 급변 알림
- 뉴스 데이터 파이프라인
- 관심분야 Radar 리포트
- 관심종목 Radar 리포트
- 파이프라인 백필 실행 및 테이블 조회

### v1 제외

- 자동매매 주문
- 증권사 계좌 연동 매매
- 코인, 옵션, 채권 지원
- 멀티 유저/권한 관리
- 유료 뉴스 원문 전문 수집

## 4. 리포트 구조

현재 최종 전략 리포트 타입은 2개다.

- `interest_area_radar`
  - 관심분야와 연관된 산업/정책/기술 변화 요약
  - 연결 종목 후보
  - 감시 포인트
- `interest_stock_radar`
  - 관심종목과 직접 연결된 뉴스 이벤트
  - 단기 모멘텀 및 진입 관찰 포인트
  - 추가 확인할 재료

기존 기능은 유지한다.

- `manual_codex_analysis`
- `interest_area_research_watch`
- `price_alert_watch`

## 5. 데이터 파이프라인 요구사항

뉴스 파이프라인은 다음 4단계를 분리한다.

1. Collector: 소스에서 뉴스를 수집해 `news_raw`에 저장
2. Article Fetcher: source URL에서 기사 본문을 가져와 `news_raw.raw_body`를 보강
3. Classifier: `title + raw_summary + raw_body` 기준으로 종목/섹터/중요도/감성/사용자 연결을 추출해 `news_refined`에 저장
4. Market Reporter: 관련 뉴스를 테마와 내러티브로 묶어 `news_cluster`에 저장
5. Personal Strategy Reporter: `news_cluster`와 사용자 컨텍스트를 결합해 최종 `report`, `strategy_report`를 생성

수집 정책은 다음을 따른다.

- 최초 수집: source별 최근 7일 backfill
- 이후 수집: source별 `last_collected_at` 이후 기사만 유지
- 모든 시간 필드: ISO 8601 문자열
- 보관 기간: 30일

## 6. 성공 기준

- PWA에서 관심종목, 보유종목, 관심분야, 스케줄, 리포트를 정상 조회할 수 있다.
- 파이프라인 체인이 `news_collect -> news_classify -> market_cluster` 순서로 주기 실행된다.
- 서버 재시작 시 중간에 멈춘 단계부터 자동 재개된다.
- 사용자가 `POST /api/pipeline/backfill` 또는 프론트 버튼으로 백필을 실행할 수 있다.
- 파이프라인 테이블 화면에서 `news_raw`, `news_refined`, `news_cluster`, `strategy_report`, `pipeline_state`를 확인할 수 있다.
- 관심분야 Radar와 관심종목 Radar가 기존 `report` 조회 흐름과 호환된다.

## 7. 문서 운영 규칙

- 구조 변경 시 `docs/ARCHITECTURE.md`를 갱신한다.
- API/스키마 변경 시 `docs/API.md`를 갱신한다.
- 스케줄/체인 규칙 변경 시 `docs/SCHEDULER.md`를 갱신한다.
- Codex 분석 파이프라인 변경 시 `docs/CODEX_PIPELINE.md`를 갱신한다.
- 구현 계획과 남은 과제는 `docs/TODO.md`에서 추적한다.
- 의미 있는 구현 변경은 `docs/CHANGELOG.md`에 기록한다.
