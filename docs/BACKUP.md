# 백업·복구·이전·업데이트

## 내보내기로 다른 서버로 이동

기존 앱의 **설정 → 전체 ZIP 내보내기**로 메모와 첨부를 내려받고, 새 서버에서 로그인해 **ZIP 가져오기 → 미리보기 → 실행**을 선택합니다. 제목·본문·날짜·태그·폴더·첨부를 옮깁니다. 기존 ID는 덮어쓰지 않고 건너뜁니다. 로그인 정보·패스키·토큰은 ZIP에 포함하지 않으므로 새 서버에서 설정합니다.

## Docker 온라인 백업

저장소 루트에서 설치할 때 사용한 Compose 파일을 같은 순서로 전달합니다.

```sh
# 로컬
sh scripts/backup-compose.sh
# NAS·기존 프록시
sh scripts/backup-compose.sh -f compose.yaml -f compose.nas.yaml
# Caddy HTTPS·AWS
sh scripts/backup-compose.sh -f compose.yaml -f compose.https.yaml
```

실행 중인 DB에 SQLite Online Backup API를 사용하고 임시 폴더로 복원 검증을 수행한 뒤, 서버의 `backups/`에 백업을 복사합니다. 기존 파일은 덮어쓰지 않습니다. 이 백업은 메모·첨부뿐 아니라 인증 설정·API 토큰 해시·패스키 공개 키도 포함하므로 비공개로 보관하세요. 같은 디스크에만 보관하면 디스크 고장에 대비할 수 없으므로 별도 저장소에도 복사합니다.

예약 작업·자동 삭제·외부 전송은 기본으로 설치하지 않습니다. 운영 환경의 스케줄러에서 실행 시간과 보존 정책을 정하세요. 실행 중인 SQLite DB 파일을 직접 복사하지 마세요.

## Docker에서 새 볼륨으로 복원

아래는 로컬 기본 구성 기준입니다. NAS는 각 명령의 `-f compose.yaml` 뒤에 `-f compose.nas.yaml`, HTTPS 서버는 `-f compose.https.yaml`을 추가합니다. 항상 같은 프로젝트 폴더·프로젝트 이름으로 실행하세요.

1. 백업 파일을 앱 사용자 권한으로 백업 볼륨에 넣습니다. `BACKUP.sqlite3`는 실제 파일명으로 바꿉니다. 아래 입력 파일이 이미 존재하면 덮어쓰지 않고 실패합니다. 다시 시도할 때는 새 입력 파일명으로 바꾸세요.

```sh
docker compose exec -T memo sh -c 'umask 077; set -C; cat > /backups/restore-input.sqlite3' < backups/BACKUP.sqlite3
docker compose exec -T memo python scripts/verify_restore.py /backups/restore-input.sqlite3
docker compose stop memo
```

2. 제공된 복원 설정은 기존 데이터 대신 **새 `restored_data` 볼륨**을 사용합니다. 처음 복원할 때만 실행합니다. 이미 복원 데이터가 있는 볼륨에는 덮어쓰지 않고 실패합니다.

```sh
docker compose -f compose.yaml -f deploy/compose.restore.yaml run --rm --no-deps memo python scripts/restore.py /backups/restore-input.sqlite3 --to /data
docker compose -f compose.yaml -f deploy/compose.restore.yaml up -d --wait
```

3. 기존 비밀번호로 로그인해 메모·첨부를 확인합니다. 복원은 웹 세션과 임시 인증 요청을 지우며 비밀번호·토큰·패스키 설정은 보존합니다. 다른 도메인으로 옮기면 패스키를 다시 등록하세요.

이후 모든 실행·백업·업데이트에도 **`-f deploy/compose.restore.yaml`을 마지막에 유지**하세요. 생략하면 기존 데이터 볼륨으로 돌아갑니다. 기존 볼륨은 확인이 끝날 때까지 보관합니다. 다시 복원 훈련할 때는 별도 이름의 새 볼륨을 사용하세요. 사용 중인 데이터 볼륨을 삭제해서 재활용하지 마세요.

새 서버에 전체 복원할 때는 먼저 빈 앱을 실행해 컨테이너와 백업 볼륨을 만든 뒤 같은 절차로 복원합니다. 새 앱의 초기 비밀번호 대신 복원된 DB의 기존 비밀번호를 사용합니다.

## Python 직접 실행의 백업·복원

```sh
.venv/bin/python scripts/backup.py --data-dir .data --output backups/manual.sqlite3
.venv/bin/python scripts/verify_restore.py backups/manual.sqlite3
# 앱을 종료한 다음 빈 경로에 복원
.venv/bin/python scripts/restore.py backups/manual.sqlite3 --to .data-restored
MEMO_DATA_DIR=.data-restored .venv/bin/python app.py
```

## 업데이트

1. 위 방법으로 백업과 복원 검증을 완료하고 현재 커밋을 `git rev-parse HEAD`로 기록합니다.
2. 변경 내용을 확인하고 `git pull --ff-only`로 소스를 받습니다.
3. 설치할 때의 Compose 파일들로 `docker compose ... up -d --build --wait`를 실행합니다.
4. 로그인·메모·첨부·다른 기기 접속을 점검합니다.

이 공개본은 개인 운영 서버의 비공개 컨테이너 이미지와 연결하지 않으며 자동 업데이트하지 않습니다. 업데이트가 DB 구조를 바꾸면 이전 코드로 되돌리는 것만으로 복구할 수 없을 수 있습니다. 이전 소스와 검증한 백업을 함께 보관하고, 문제가 생기면 기존 데이터를 보존한 상태에서 새 빈 볼륨에 복원합니다. 업데이트 이후 작성한 메모도 별도로 보관하세요.

이전 앱과 호환되는 한줄 ZIP은 최대 256MB, 메모 2만 개, 파일 5만 개까지 가져올 수 있습니다. 큰 데이터의 전체 이전은 DB 백업·복원을 사용하세요. 자세한 데이터 형식은 [운영 문서](OPERATIONS.md)를 참고하세요.
