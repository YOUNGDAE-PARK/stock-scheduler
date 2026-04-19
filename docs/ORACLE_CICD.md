# Oracle Cloud CI/CD

이 프로젝트는 GitHub Actions가 Oracle Cloud VM에 release archive를 전송하고, VM에서 Docker Compose를 재빌드/재시작하는 방식으로 배포한다. 1GB 무료 VM에서는 PostgreSQL을 빼고 SQLite 파일 DB를 쓰는 `docker-compose.oracle-lite.yml`을 기본 배포 대상으로 사용한다.

## 1. Oracle Cloud에서 먼저 할 일

1. Compute Instance를 만든다.
   - Image: Ubuntu 22.04 또는 24.04
   - Shape: Always Free 가능 shape
   - SSH public key 등록
2. VCN Security List 또는 Network Security Group에서 ingress를 연다.
   - TCP 5173: PWA frontend
   - TCP 8000: backend API. 외부 공개가 부담되면 추후 nginx reverse proxy 뒤로 숨긴다.
   - TCP 22: SSH
3. VM에 SSH 접속 후 bootstrap을 한 번 실행한다.

```bash
bash scripts/oracle-bootstrap.sh
```

GitHub Actions가 배포를 수행하므로 서버에는 `/opt/stock_scheduler` 디렉터리와 Docker만 준비되면 된다.

서버 내부 방화벽도 5173/8000을 허용해야 한다. `oracle-bootstrap.sh`는 iptables에 5173/8000 허용 규칙을 추가하고 `netfilter-persistent`로 저장한다.

## 2. GitHub Secrets

이미 설정한 앱 secret 외에 배포용 secret/variable이 추가로 필요하다.

Repository variables:

- `OCI_HOST`: Oracle VM public IP 또는 DNS
- `OCI_USER`: SSH 사용자. Ubuntu image면 보통 `ubuntu`
- `TELEGRAM_CHAT_ID`: Telegram 메시지를 받을 chat id. Secret으로 넣어도 된다.
- `KIS_ENV`: `virtual` 또는 `real`. 없으면 `virtual`로 배포한다.
- `DEPLOY_COMPOSE_FILE`: 배포 compose 파일. 없으면 `docker-compose.oracle-lite.yml`이다.
- `KIS_REAL_BASE_URL`: 기본값 `https://openapi.koreainvestment.com:9443`
- `KIS_VIRTUAL_BASE_URL`: 기본값 `https://openapivts.koreainvestment.com:29443`

배포 workflow는 `CORS_ALLOW_ORIGINS=http://<OCI_HOST>:5173`을 `.env`에 자동으로 넣는다.

Repository secrets:

- `OCI_SSH_PRIVATE_KEY`: VM에 접속 가능한 private key 전체
- `CODEX_AUTH_JSON`: 로컬 `secrets/codex/auth.json` 파일 내용 전체
- `GEMINI_OAUTH_CREDS_JSON`: 로컬 `~/.gemini/oauth_creds.json` 파일 내용 전체. `ORCHESTRATOR_TYPE=gemini`일 때 필요하다.
- `TELEGRAM_BOT_TOKEN`
- `KIS_REAL_APP_KEY`
- `KIS_REAL_APP_SECRET`
- `KIS_VIRTUAL_APP_KEY`
- `KIS_VIRTUAL_APP_SECRET`

선택 secret:

- `POSTGRES_PASSWORD`: 운영 PostgreSQL 비밀번호. 없으면 기본값을 쓴다.

## 3. 배포 방식

- `CI` workflow는 push/PR에서 backend test, frontend build, compose config를 검증한다.
- `Deploy Oracle` workflow는 수동 실행으로 동작한다. Oracle VM과 SSH secret이 준비되기 전 push 배포 실패를 막기 위해 자동 배포는 아직 켜지지 않았다.
- 배포 시 GitHub Actions가 `.env`, `secrets/codex/auth.json`, `secrets/gemini/oauth_creds.json`, release archive를 VM으로 전송한다.
- VM에서는 `docker compose -f docker-compose.oracle-lite.yml up -d --build`가 실행된다.
- SQLite DB 파일은 `/opt/stock_scheduler/stock_scheduler.db`에 저장되고 backend 컨테이너의 `/app/stock_scheduler.db`로 bind mount된다.

PostgreSQL로 운영하려면 repository variable `DEPLOY_COMPOSE_FILE=docker-compose.yml`로 바꾸고, VM 메모리를 2GB 이상으로 잡는 것을 권장한다.

## 4. SQLite 백업

lite compose를 사용할 때는 VM에서 아래 스크립트로 DB 파일을 백업할 수 있다.

```bash
cd /opt/stock_scheduler
scripts/oracle-backup-sqlite.sh
```

14일이 지난 백업은 자동 삭제한다. 필요하면 cron에 등록한다.

## 5. 운영 확인

```bash
docker compose ps
curl http://localhost:8000/api/health
curl http://localhost:8000/api/diagnostics/codex
```

브라우저에서는 다음 주소를 연다.

```text
http://<OCI_HOST>:5173/
```

서버 내부에서는 응답하지만 외부 접속이 timeout이면 Oracle Console에서 다음 경로를 확인한다.

```text
Networking → Virtual cloud networks → <VCN> → Security Lists → Default Security List → Add Ingress Rules
```

필수 ingress rule:

```text
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 5173
```

```text
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 8000
```
