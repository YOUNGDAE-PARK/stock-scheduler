# stock_scheduler

국내/미국 주식의 관심종목, 관심분야, 보유종목, 스케줄, 알림, Codex 기반 분석을 관리하는 FastAPI + APScheduler + SQLite/PostgreSQL 백엔드와 React/Vite PWA 프로젝트다.

## Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

기본 DB는 `stock_scheduler.db`다. 다른 SQLite 파일을 쓰려면 `DATABASE_URL=sqlite:///./local.db`를 지정한다.

## Dev Server

프론트와 백엔드를 한 번에 실행하려면 WSL에서 아래 스크립트를 사용한다.

```bash
./scripts/start-dev.sh
```

기본 주소는 다음과 같다.

```text
PC:      http://localhost:5173
휴대폰:  http://10.0.0.2:5173
```

휴대폰 접속 주소가 바뀌면 `HOST_IP`를 지정한다.

```bash
HOST_IP=192.168.0.12 ./scripts/start-dev.sh
```

## Docker Compose

Oracle Cloud 같은 서버에서는 Docker Compose로 PostgreSQL, backend, frontend를 함께 실행할 수 있다.

```bash
docker compose up -d --build
```

Compose 실행 시 backend는 PostgreSQL을 사용한다.

```text
DATABASE_URL=postgresql://stock_scheduler:stock_scheduler@db:5432/stock_scheduler
Frontend: http://SERVER_IP:5173
Backend:  http://SERVER_IP:8000
```

`TELEGRAM_*`, `KIS_*` 같은 비밀값은 `.env`에 입력한다. Backend 이미지는 Codex CLI를 설치한다. Codex 인증은 사용자가 직접 프로젝트의 `secrets/codex/auth.json`에 저장하고, Docker Compose는 이 파일만 컨테이너의 `/root/.codex/auth.json`에 read-only로 mount한다. `/root/.codex` 디렉터리 자체는 Codex가 상태 파일을 쓸 수 있도록 writable로 둔다.

수동 저장 절차는 다음과 같다.

```bash
mkdir -p secrets/codex
cp ~/.codex/auth.json secrets/codex/auth.json
```

Oracle Cloud에서는 로컬 PC에서 만든 `auth.json`을 서버의 프로젝트 폴더 아래 `secrets/codex/auth.json`로 업로드해도 된다. `secrets/codex/auth.json`은 `.gitignore` 대상이라 저장소에 올라가지 않는다.

Codex 인증 인식 여부는 아래 endpoint로 확인한다. 응답은 파일 존재 여부만 보여주며 토큰 내용은 노출하지 않는다.

```bash
curl http://localhost:8000/api/diagnostics/codex
```

WSL Docker에서 bridge networking의 외부 HTTPS 연결이 막히는 경우에는 override 파일을 함께 사용한다. 이 override는 backend를 host network로 실행해 Codex CLI가 WSL 호스트의 네트워크를 사용하게 한다.

```bash
docker-compose -f docker-compose.yml -f docker-compose.wsl.yml up -d --build
```

Oracle Cloud CI/CD 구성은 `docs/ORACLE_CICD.md`를 따른다.

1GB Oracle 무료 VM에서는 PostgreSQL 대신 SQLite 파일 DB를 쓰는 lite compose를 권장한다.

```bash
docker compose -f docker-compose.oracle-lite.yml up -d --build
```

### 한국투자증권 Open API 설정

직접 입력할 파일 이름은 프로젝트 루트의 `.env`다. `.env.example`은 공유용 템플릿이고, 실제 비밀값은 `.env`에만 입력한다.

```bash
# .env 파일이 없을 때만 실행
cp .env.example .env
```

모의투자를 쓰려면 `KIS_ENV=virtual`, 실전투자를 쓰려면 `KIS_ENV=real`로 바꾼다.

```dotenv
KIS_ENV=virtual
KIS_VIRTUAL_APP_KEY=모의_APP_KEY
KIS_VIRTUAL_APP_SECRET=모의_APP_SECRET

KIS_REAL_APP_KEY=실전_APP_KEY
KIS_REAL_APP_SECRET=실전_APP_SECRET
```

토큰 발급에는 내부적으로 `KIS_GRANT_TYPE=client_credentials`와 선택된 환경의 `APP_KEY`, `APP_SECRET`, `/oauth2/tokenP` URL을 사용한다.
접근토큰은 앱 프로세스 메모리에 캐시되어 만료 전까지 재사용되며, 토큰 오류가 발생하면 캐시를 지우고 1회 재발급 후 요청을 재시도한다.

### Telegram 알림 설정

실제 휴대폰 알림은 Telegram Bot API로 보낼 수 있다. `.env`에 아래 값을 입력한다.

```dotenv
NOTIFICATION_MODE=telegram
TELEGRAM_BOT_TOKEN=발급받은_봇_토큰
TELEGRAM_CHAT_ID=내_개인_CHAT_ID
```

`/api/notifications/test`와 PWA의 알림 테스트 버튼은 `NOTIFICATION_MODE=telegram`일 때 실제 Telegram 메시지를 보내고, 결과를 `notification_log`에 기록한다.

## 관심분야 연구성과 감지

PWA의 자연어 명령창에서 관심분야를 추가한다. 예: `AI 반도체를 관심분야로 추가하고 키워드는 HBM, 온디바이스 AI, 연결 종목은 삼성전자와 SK하이닉스`. Codex orchestrator가 이를 내부 format인 category, keywords, linked tickers, memo로 구조화한다. 기본 스케줄 `09:00 관심분야 연구성과 감지`는 활성 관심분야를 전용 Codex skill로 점검하고, 연결 종목 전망에 의미 있는 주요 성과가 감지되면 Telegram으로 리포트 본문까지 보낸다.

## 개인화 전략 리포트

내부 뉴스 파이프라인은 RSS/search headline provider와 사용자가 추가한 RSS/feed 소스를 수집해 `관심분야 Radar`, `관심종목 Radar`, `보유종목 Decision` 리포트를 생성한다. 리포트는 단순 소스 나열이 아니라 headline 흐름을 바탕으로 연결 종목, 감시 포인트, 액션 의견을 정리한다.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

PWA는 기본적으로 `http://localhost:8000` API를 호출한다. 다른 API 주소를 쓰려면 `VITE_API_BASE`를 설정한다.

## Tests

```bash
pytest backend/tests
```
