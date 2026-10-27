# 로컬 PC에서 사용

## Docker

Docker Desktop 또는 Docker Engine + Compose v2를 준비합니다. 저장소 루트에서:

```sh
docker compose up -d --build --wait
docker compose exec memo cat /data/initial-password.txt
```

`http://localhost:8787`을 열고 최초 비밀번호를 변경합니다. 기본 포트는 PC의 루프백에만 연결되므로 다른 기기에서 PC의 IP로 접속할 수 없습니다. 원격 사용은 [서버 HTTPS 구성](SERVER.md)을 따르세요.

```sh
docker compose logs --tail 100 memo
docker compose restart memo
docker compose down
```

마지막 명령은 컨테이너를 중지·제거하고 메모 볼륨은 보존합니다. `docker compose down -v`나 볼륨 삭제는 메모와 백업을 삭제할 수 있습니다. 폴더 이름이나 Compose 프로젝트 이름을 바꾸면 다른 볼륨을 사용하므로 이전 데이터가 사라진 것처럼 보일 수 있습니다. 처음 사용한 프로젝트 이름을 유지하세요.

## Python 직접 실행

Python 3.11 이상과 FTS5 trigram을 지원하는 SQLite 3.34 이상이 필요합니다. 먼저 현재 Python의 SQLite를 확인합니다.

```sh
python3 -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE probe USING fts5(body, tokenize='trigram')\"); print(sqlite3.sqlite_version)"
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
.venv/bin/python app.py
```

최초 비밀번호는 `.data/initial-password.txt`에 있습니다. 별도 터미널에서 `cat .data/initial-password.txt`로 읽고 `http://localhost:8787`에 로그인합니다. 종료는 `Ctrl+C`이고 같은 명령으로 다시 실행하면 데이터가 유지됩니다. macOS 기본 Python의 SQLite가 오래되면 새로운 Python 설치나 Docker를 사용하세요. Windows에서는 `.venv\Scripts\python.exe`, `.venv\Scripts\pip.exe`를 사용합니다.

포트와 저장 폴더를 바꾸는 예:

```sh
MEMO_DATA_DIR=/absolute/path/to/private-data PORT=8790 MEMO_PUBLIC_ORIGIN=http://localhost:8790 .venv/bin/python app.py
```

데이터 폴더는 전용 로컬 디스크 경로로 정하고 클라우드 동기화 폴더나 네트워크 공유에 DB를 두지 마세요. `.env.example`은 직접 실행용 환경변수 설명이며 Python이 자동으로 불러오는 파일은 아닙니다.
