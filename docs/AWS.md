# AWS EC2에 설치

이 안내는 **EC2 한 대 + 영속 EBS 디스크 + Docker Compose + Caddy HTTPS** 구성입니다. AWS 리소스를 자동 생성하지 않습니다. 본인의 AWS 계정과 도메인을 사용하며 EC2·EBS·네트워크·백업 등 사용 요금은 AWS 설정에 따라 발생합니다. 무료 사용을 보장하지 않습니다.

## 1. 서버와 네트워크 준비

EC2에서 Docker를 지원하는 Ubuntu LTS 인스턴스를 준비합니다. CPU 아키텍처는 amd64 또는 arm64를 사용할 수 있으며 소스를 해당 서버에서 빌드합니다. 용량은 메모와 첨부 규모에 맞추고 빌드·백업을 위한 여유 공간을 둡니다.

EBS 영속 디스크를 사용하고 중요 데이터는 암호화된 볼륨에 저장하세요. 루트 볼륨도 EBS이지만 인스턴스 종료 시 함께 삭제될 수 있으므로 **Delete on termination 설정**과 백업 정책을 확인하세요. 별도 EBS를 사용한다면 Docker 데이터 디렉터리가 그 디스크를 사용하도록 사전에 구성하고 재부팅 후 마운트도 확인합니다. 기본 Docker 볼륨은 Docker 데이터 디렉터리에 저장됩니다.

| 보안 그룹 인바운드 | 허용 범위 |
| --- | --- |
| TCP 22 / SSH | 관리자 IP만 허용하거나 Session Manager 사용 |
| TCP 80 / HTTP | 웹 접속·인증서 발급이 도달할 범위 |
| TCP 443 / HTTPS | 웹 접속이 도달할 범위 |
| TCP 8787 | 외부에 열지 않음 |

인터넷 공개 접속을 원하면 80/443을 인터넷에서 도달하게 하고, SSH는 관리자 IP로 제한합니다. IPv6 사용 시 실제 라우팅과 IPv6 규칙을 함께 설정합니다. [AWS 공식 보안 그룹 예시](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html)를 참고하세요.

도메인을 인스턴스의 고정 주소로 연결하세요. 주소 변경을 막으려면 Elastic IP 같은 고정 주소 방식을 검토하되 요금도 확인합니다. 사용자용 서버리스 임시 파일시스템이나 인스턴스 스토어를 SQLite 영속 저장소로 사용하지 않습니다.

## 2. Docker와 앱 설치

SSH 등으로 서버에 접속해 [Docker의 Ubuntu 설치 안내](https://docs.docker.com/engine/install/ubuntu/)에 따라 Docker Engine, Buildx, Compose 플러그인을 설치합니다. `git`, `curl`도 준비합니다. `docker` 실행 권한이 없으면 적절한 서버 계정 권한을 설정하거나 명령 앞에 `sudo`를 붙이세요.

```sh
git clone https://github.com/stranger828/hanjul-selfhosted.git
cd hanjul-selfhosted
cp deploy/server/env.example .env
```

`.env`의 `HANJUL_DOMAIN`을 본인 도메인으로 바꿉니다.

```sh
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.https.yaml exec memo cat /data/initial-password.txt
```

브라우저에서 `https://본인도메인`에 접속해 로그인하고 비밀번호를 변경합니다. [서버 안내의 설치 후 점검](SERVER.md)을 수행합니다. AWS 키를 앱이나 `.env`에 넣을 필요가 없습니다.

## 3. 백업과 재시작 확인

```sh
sh scripts/backup-compose.sh -f compose.yaml -f compose.https.yaml
docker compose -f compose.yaml -f compose.https.yaml restart memo
```

메모·첨부·로그인 상태를 점검합니다. 백업 스크립트는 온라인 백업, 새 임시 폴더 복원 검증, 서버의 `backups/`로 복사를 수행합니다. EBS 스냅샷만 의존하지 말고 이 검증된 백업도 서버 밖에 보관하세요. S3를 선택한다면 비공개 버킷, 암호화, 최소 권한 IAM 역할과 보존 정책을 사용하세요. 이 저장소는 S3 전송이나 예약을 자동 설정하지 않습니다.

[AWS EBS 스냅샷 문서](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html) · [앱 백업·복구](BACKUP.md)

AWS 실계정에서 인스턴스·도메인을 생성하는 검증은 수행하지 않았습니다. 배포 파일과 앱 검증 범위는 [검증 기록](VALIDATION.md)에 구분합니다.
