# Synology·개인 NAS에 설치

Docker Compose v2와 컨테이너 실행을 지원하는 NAS, 영속 로컬 볼륨, HTTPS 역방향 프록시를 준비합니다. Synology에서는 지원 모델의 Container Manager를 사용합니다. [공식 지원·릴리스 안내](https://www.synology.com/en-us/releaseNote/ContainerManager)를 확인하세요.

## 소스 준비

NAS의 전용 프로젝트 폴더에 이 공개 저장소를 복제하거나 ZIP을 다운로드해 풉니다. 예시 경로는 `/volume1/docker/hanjul-selfhosted`이며 실제 볼륨에 맞게 선택합니다. 공개 소스는 로그인·GitHub 토큰 없이 받을 수 있습니다.

```sh
git clone https://github.com/stranger828/hanjul-selfhosted.git
cd hanjul-selfhosted
cp deploy/synology/env.example .env
```

`.env`에 브라우저로 열 주소를 지정합니다.

```dotenv
MEMO_PUBLIC_ORIGIN=https://notes.example.com
```

예시 도메인은 본인의 도메인·DDNS로 바꾸세요. 경로나 끝의 `/`는 넣지 않습니다.

## 컨테이너 실행

SSH 터미널이 있으면 저장소 루트에서 실행합니다.

```sh
docker compose -f compose.yaml -f compose.nas.yaml config --quiet
docker compose -f compose.yaml -f compose.nas.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.nas.yaml exec memo cat /data/initial-password.txt
```

앱은 이미지의 전용 사용자 UID/GID `10001:10001`로 실행하며 Docker 관리 볼륨에 저장합니다. 호스트의 개인 UID나 폴더 권한을 그대로 복사할 필요가 없습니다. 데이터는 해당 NAS 디스크에 저장되며 NAS 외부 백업은 별도로 필요합니다.

Container Manager의 프로젝트 UI만 사용한다면 소스 폴더 전체를 올리고 두 Compose 파일을 병합한 설정으로 프로젝트를 만듭니다. PC에서 병합 파일을 생성할 수 있습니다.

```sh
docker compose --env-file .env -f compose.yaml -f compose.nas.yaml config --no-path-resolution > compose.nas.generated.yaml
```

생성 파일의 `build.context`가 `.`인지 확인한 뒤 NAS 소스 폴더에 함께 업로드하고 프로젝트의 설정으로 사용합니다. 이 파일에는 지정한 도메인이 포함되므로 Git에 올리지 않습니다. UI 기능·메뉴명은 DSM 버전에 따라 다를 수 있고, 터미널의 `docker compose` 경로가 가장 직접적입니다. 최초 비밀번호는 컨테이너 터미널에서 `cat /data/initial-password.txt`로 읽습니다.

## NAS HTTPS 프록시

1. DNS·DDNS를 NAS에 연결하고 해당 도메인에 유효한 인증서를 준비합니다.
2. DSM 역방향 프록시에서 소스를 `HTTPS / 본인 도메인 / 443`, 대상을 `HTTP / 127.0.0.1 / 8787`로 지정합니다.
3. 인증서를 같은 도메인의 프록시에 배정하고 원래 Host 헤더를 보존합니다.
4. 인터넷 사용 시 공유기·방화벽에서 이 HTTPS 경로가 도달하는지 확인합니다. 앱 포트 8787을 외부에 열지 않습니다.
5. `https://본인도메인`에서 최초 로그인 후 비밀번호를 변경합니다.

패스키는 HTTPS 도메인에 연결됩니다. 프록시와 `MEMO_PUBLIC_ORIGIN`이 다르면 인증·저장이 실패할 수 있습니다. NAS 안의 별도 프록시 컨테이너를 쓴다면 [서버 네트워크 설명](../../docs/SERVER.md)을 참고하세요.

## 백업·업데이트

```sh
sh scripts/backup-compose.sh -f compose.yaml -f compose.nas.yaml
```

NAS 작업 스케줄러에는 저장소로 `cd`한 뒤 위 명령을 실행하는 작업을 직접 등록할 수 있습니다. 작업 계정은 Docker 명령 실행 권한이 필요합니다. 예약 시간과 보존 기간은 본인이 정합니다. 이 저장소는 자동 예약·개인 NAS 접속·개인 운영 업데이트를 설정하지 않습니다.

[백업·복원·업데이트 절차](../../docs/BACKUP.md)를 따르세요. 새 서버로 옮기면 ZIP 가져오기 또는 검증한 DB 백업을 사용합니다. NAS의 컨테이너 재시작 후에도 메모·첨부가 보존되는지 확인하세요.
