# 공개본 검증과 재현 방법

이 문서는 공개용 소스의 검증 범위를 기록합니다. 개인 NAS 주소·운영 로그·실제 메모·과거 비공개 배포 이력은 공개 저장소에 포함하지 않습니다.

## 앱 검증

API·인증·검색·첨부·ZIP 이동·폴더·백업/복원과 실제 Chromium의 메모 편집·표·이미지·클립보드·패스키·기기 간 갱신 테스트를 제공합니다. 모든 데이터베이스는 임시 경로, 브라우저는 분리한 프로필을 사용하며 문서 화면에는 합성 테스트 메모만 표시합니다.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
HANJUL_TEST_CHROME="$(.venv/bin/python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()')" .venv/bin/python -m pytest -q
```

2026-10-27 macOS arm64 / Python 3.14 / 분리된 Google Chrome 프로필에서 **전체 76개 테스트 통과**(137.69초)를 확인했습니다. 공개 배포 파일이 모두 소스 묶음에 포함되는 운영 테스트 3개도 변경 후 재실행해 통과했습니다. JavaScript 구문 검사, 셸 구문 검사, 문서 파일 링크 점검과 소스 배포 묶음 생성도 통과했습니다.

Docker Engine이 없는 로컬 환경에서는 컨테이너 실행을 확인하지 않았습니다. Linux의 실제 Docker 빌드·Compose·HTTPS·복원 결과는 아래 GitHub Actions 기록으로 확인합니다.

## 2026-10-27 공개본 검증 결과

[GitHub Actions 성공 실행](https://github.com/stranger828/hanjul-selfhosted/actions/runs/40425855471)에서 Ubuntu 24.04 / Python 3.14 환경의 전체 API·브라우저 테스트와 실제 Docker 통합 검증이 모두 통과했습니다.

| 항목 | 결과 |
| --- | --- |
| 전체 API·브라우저 테스트 | 통과 |
| 로컬·NAS·HTTPS·복원 Compose 설정 | 통과 |
| Docker 이미지 빌드·실행 | 통과 |
| 미인증 메모 차단·로그인·메모 생성 | 통과 |
| 재시작 후 메모 유지 | 통과 |
| 온라인 백업·임시 복원 검증 | 통과 |
| 새 데이터 볼륨 복원·세션 정리 | 통과 |
| Caddy 설정·로컬 HTTPS 접속 | 통과 |
| 소스 전용 배포 묶음 | 통과 |

README의 PC·휴대폰 소개 화면은 `scripts/capture_demo.py`로 별도 임시 DB의 예시 메모를 촬영하고 시각 확인했습니다. 개인 메모를 사용하지 않습니다.

## 배포 구성 검증

[GitHub Actions](https://github.com/stranger828/hanjul-selfhosted/actions)는 전체 테스트 외에 다음을 수행합니다.

1. 로컬·NAS·Caddy HTTPS·복원용 Compose 설정을 검증합니다.
2. 이미지를 실제로 빌드하고 격리된 Compose 프로젝트로 실행합니다.
3. 미인증 메모 접근 차단, 로그인과 메모 생성, 재시작을 확인합니다.
4. 온라인 백업과 임시 폴더 복원 검증 후 새 데이터 볼륨에 복원합니다.
5. 복원된 메모와 웹 세션 초기화를 확인합니다.
6. 로컬 인증서를 사용하는 Caddy HTTPS 경로와 설정을 확인합니다. 테스트의 `curl --insecure`는 임시 인증서 검사에만 사용합니다.
7. 실사용 데이터가 제외된 소스 묶음을 생성합니다.

`scripts/verify-compose.sh`는 CI용이며 임시 프로젝트와 그 볼륨을 생성·삭제합니다. 실제 운영 앱의 테스트 명령으로 사용하지 마세요.

NAS 실기기와 AWS 실계정에서 새 서버를 생성·설치하는 작업은 이 공개본 검증에 포함하지 않습니다. DNS·인증서·포트·권한·디스크는 설치할 환경에서 [설치 후 확인](SELF-HOSTING.md#설치-후-확인)을 수행하세요. CI의 localhost HTTPS 점검은 인터넷 인증서 발급 검증을 대신하지 않습니다.

## 공개 소스 점검

공개본은 소스 파일을 선별해 새 Git 이력으로 만들었습니다. 실제 DB·백업·환경변수·인증 파일·개인 배포 이력은 복사하지 않습니다. `.gitignore`로 런타임 데이터를 제외하고, `scripts/package_release.py`도 허용한 소스만 묶습니다. 소스와 문서에서 개인 운영 주소와 대표적인 비밀키 형식을 확인합니다.
