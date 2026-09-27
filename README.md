# BOA

React(Vite) 프론트엔드 + FastAPI 백엔드 모노레포.

```
frontend/   React 19 + Vite 8 + TypeScript   → 로컬에서 직접 실행 (나중에 Vercel 배포)
backend/    FastAPI + PostgreSQL 17           → API는 Docker, DB는 각자 PC에 설치 (나중에 EC2 + RDS 배포)
```

| 항목 | 버전 |
|---|---|
| Node / pnpm | 24 LTS / 10 |
| Python | 3.12 (Docker 이미지) |
| PostgreSQL | 17 (각자 PC에 설치) |

## 처음 한 번 설치

### 공통
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Node 24 — 아래 OS별 방법 참고
- pnpm: `npm install -g pnpm@10`

### Windows
1. BIOS에서 가상화(VT-x / AMD-V)가 켜져 있는지 확인
2. PowerShell(관리자)에서 `wsl --install` → **재부팅**
3. `wsl -l -v`로 VERSION이 2인지 확인 (1이면 `wsl --set-version Ubuntu 2`)
4. Docker Desktop 설치 (Settings → General → "Use the WSL 2 based engine" 체크)
5. Node 설치: `winget install Schniz.fnm` → `fnm install 24` → `fnm use 24`
   - PowerShell 프로필에 `fnm env --use-on-cd | Out-String | Invoke-Expression` 추가
6. Git 줄바꿈 설정은 저장소의 `.gitattributes`가 처리하므로 따로 할 필요 없음

7. PostgreSQL 17 설치: [EDB 설치 프로그램](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads)로 설치 (포트 `5432`, 설치 중 정한 `postgres` 비밀번호는 기억해둘 것)

### Mac
```sh
brew install fnm && fnm install 24
brew install postgresql@17 && brew services start postgresql@17
```

### DB 만들기 (Mac/Windows 공통, 처음 한 번)
```sh
# Mac은 비밀번호 없이, Windows는 설치 때 정한 postgres 비밀번호 입력
psql -h localhost -U postgres -d postgres -c "CREATE ROLE boa LOGIN PASSWORD 'boa';"   # Mac: -U postgres 빼기
psql -h localhost -U postgres -d postgres -c "CREATE DATABASE boa OWNER boa;"          # Mac: -U postgres 빼기
```
그 다음 DBeaver 등에서 `boa` DB에 접속해 팀 스키마 SQL을 실행한다.
- `psql`을 못 찾으면 Mac은 `/opt/homebrew/opt/postgresql@17/bin/psql`, Windows는 `C:\Program Files\PostgreSQL\17\bin\psql.exe`로 실행

## 실행

### 백엔드 (터미널 1)
```sh
cd backend
cp .env.example .env        # 처음 한 번 (Windows: copy .env.example .env)
docker compose up --build
```
- PostgreSQL이 먼저 켜져 있어야 한다 (Mac: `brew services start postgresql@17`, Windows: 설치 시 자동 실행)
- API 문서: http://localhost:8000/api/docs
- 컨테이너가 시작될 때 DB 마이그레이션(`alembic upgrade head`)이 자동으로 실행됨
- 코드를 수정하면 서버가 자동으로 재시작됨

### 프론트엔드 (터미널 2)
```sh
cd frontend
pnpm install
pnpm dev
```
- http://localhost:5173 — 화면에 API/DB 상태가 나오면 연결 성공
- 프론트에서는 항상 `/api/...` 경로로 호출 (Vite가 `localhost:8000`으로 전달)

## DB 스키마 변경 (Alembic)

모든 명령은 `backend/`에서 **컨테이너 안으로** 실행한다 (Mac/Windows 동일).

```sh
# 1. app/models/ 에서 모델 수정 (새 모델 파일이면 app/models/__init__.py 에 import 추가)
# 2. 마이그레이션 파일 생성
docker compose exec api alembic revision --autogenerate -m "add users table"
# 3. alembic/versions/ 에 생긴 파일을 열어서 내용 확인 후 적용
docker compose exec api alembic upgrade head
# 4. 모델 변경 + 마이그레이션 파일을 같이 커밋
```

팀원이 올린 마이그레이션을 pull 받았으면 `docker compose up`을 다시 하거나 `docker compose exec api alembic upgrade head`.

**규칙**
- main에 머지된 마이그레이션 파일은 수정하지 않는다. 고칠 게 있으면 새 마이그레이션을 만든다.
- 자동 생성 결과는 반드시 확인한다. 컬럼 이름 변경은 "삭제 후 추가"로 잘못 잡히는 경우가 있다.
- `Multiple head revisions` 에러가 나면: `docker compose exec api alembic merge heads -m "merge"`

## 자주 쓰는 명령

| 하려는 것 | 명령 (`backend/`에서) |
|---|---|
| 서버 끄기 | `docker compose down` |
| 의존성 추가 후 재빌드 | `uv add <패키지>` → `docker compose up --build` |
| DB 직접 접속 | `psql -h localhost -U boa -d boa` |
| 로그 보기 | `docker compose logs -f api` |

DB GUI(DBeaver, DataGrip 등)로 접속할 때: `localhost:5432` / 사용자 `boa` / 비밀번호 `boa` / DB `boa`

## 이미지 업로드 (S3)

AWS가 준비되기 전까지는 `.env`의 `S3_BUCKET`을 비워둔다. 이 경우 `/api/images` API는 503을 반환하고 나머지 기능은 정상 동작한다.

흐름: `POST /api/images/upload-url`로 presigned URL 발급 → 브라우저가 S3에 직접 `PUT` → `POST /api/images`로 key 저장.

## 에디터 자동완성 (선택)

Python은 컨테이너 안에서만 돌기 때문에 VS Code에서 import에 빨간 줄이 뜰 수 있다.
[uv](https://docs.astral.sh/uv/)를 설치하고 `backend/`에서 `uv sync` 후, VS Code 인터프리터로 `backend/.venv`를 선택하면 된다. (실행은 계속 Docker로)

## 문제 해결

- **`port is already allocated`**: 8000 / 5173 포트를 다른 프로그램이 쓰고 있음
- **API가 DB에 연결 못 함 (`connection refused`)**: PostgreSQL이 켜져 있는지 확인 (Mac: `brew services list`)
- **`/bin/sh^M: not found`**: 스크립트 줄바꿈이 CRLF로 바뀐 것. VS Code 우측 하단의 `CRLF`를 눌러 `LF`로 바꾸고 저장한 뒤 `docker compose up --build`
- **코드 수정이 반영 안 됨**: `docker compose logs api`에 "WatchFiles detected changes"가 찍히는지 확인
- **import 경로 대소문자**: Windows에서는 `./button`과 `./Button`이 둘 다 되지만 배포 서버(Linux)에서는 빌드가 실패한다. 파일명과 정확히 맞출 것
