# 홈 서버·Linux 서버에서 HTTPS로 사용

단일 서버와 영속 로컬 디스크를 준비합니다. 아래는 Docker Engine + Compose v2가 설치된 서버 기준입니다. Ubuntu 설치 방법은 [Docker 공식 안내](https://docs.docker.com/engine/install/ubuntu/)를 따르세요.

## Caddy와 함께 시작

1. `notes.example.com`처럼 사용할 도메인의 DNS A/AAAA를 이 서버로 연결합니다. AAAA는 실제 IPv6 경로가 있을 때만 설정합니다.
2. 공유기·서버 방화벽에서 TCP 80·443이 서버에 도달하도록 설정합니다. 이미 NAS 프록시가 이 포트를 쓰면 아래의 기존 프록시 구성을 사용하세요.
3. 다음 명령으로 소스를 받고 설정합니다.

```sh
git clone https://github.com/stranger828/hanjul-selfhosted.git
cd hanjul-selfhosted
cp deploy/server/env.example .env
```

`.env`의 `HANJUL_DOMAIN=notes.example.com`을 본인 도메인으로 바꿉니다. `https://`나 경로는 붙이지 않습니다.

```sh
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.https.yaml exec memo cat /data/initial-password.txt
```

`https://본인도메인`에 접속하고 비밀번호를 변경합니다. Caddy는 DNS·외부 접근 조건이 맞으면 인증서를 발급·갱신합니다. [Caddy 자동 HTTPS 조건](https://caddyserver.com/docs/automatic-https)을 참고하세요. 인증서 오류가 나면 Caddy 로그에서 도메인과 80/443 경로를 확인합니다. 컨테이너 정상 상태만으로 인증서 발급 성공이 확인되는 것은 아닙니다.

```sh
docker compose -f compose.yaml -f compose.https.yaml logs --tail 100 caddy memo
curl --fail https://본인도메인/healthz
```

`/healthz`는 `{"status":"ok"}`를 반환합니다. 인증하지 않은 `/api/notes` 요청은 401이어야 합니다. 앱 8787 포트를 인터넷에 개방할 필요가 없습니다. 서버 재부팅 후 Docker 서비스도 시작되도록 설정하세요.

## 기존 HTTPS 프록시에 연결

`cp deploy/synology/env.example .env` 후 `MEMO_PUBLIC_ORIGIN=https://본인도메인`으로 바꿉니다.

```sh
docker compose -f compose.yaml -f compose.nas.yaml up -d --build --wait
```

호스트에서 실행하는 프록시는 `http://127.0.0.1:8787`로 전달하고 원래 Host 헤더를 보존합니다. 프록시가 다른 컨테이너 안에서 실행된다면 그 컨테이너의 `127.0.0.1`은 한줄이 아닙니다. 공통 Docker 네트워크를 연결해 `memo:8787`을 대상으로 설정하세요. 소스 앱과 API 모두 같은 도메인의 루트에서 제공합니다.

프록시 업로드 크기와 타임아웃도 조정하세요. 앱의 ZIP 업로드 최대 크기는 256MB이고 첨부는 파일당 20MB입니다. Caddy 기본 구성은 접근 로그를 별도로 켜지 않습니다. 다른 프록시에서는 검색어가 URL 쿼리로 로그에 남을 수 있습니다.

## 유지 관리

[백업·복구·업데이트](BACKUP.md)를 사용하세요. TLS, 운영체제와 의존성 업데이트, 디스크 용량, 서버 밖 백업은 운영자가 관리합니다. SQLite 데이터는 단일 서버의 로컬 영속 디스크에 둡니다. 서버 여러 대에서 DB 파일을 공유하지 않습니다.
