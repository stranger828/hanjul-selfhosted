# 한줄 API v1

기본 URL: `http://localhost:8787/api` (운영 환경은 HTTPS 필수). 기계가 읽는 명세는 [openapi.json](openapi.json)입니다. 외부 도구와 UI는 동일한 API와 데이터를 사용합니다.

## 인증

설정에서 이름과 `read` 또는 `write` 권한을 선택해 토큰을 발급합니다. 토큰은 발급 응답에서 한 번만 보이고 서버에는 SHA-256 해시만 저장됩니다. `Authorization: Bearer <token>` 헤더로 전달합니다. `read`는 메모/첨부 GET만, `write`는 읽기와 메모 생성·수정·휴지통·첨부를 허용합니다. 토큰으로 다른 토큰 관리나 전체 내보내기/가져오기는 할 수 없습니다. 설정에서 폐기하면 다음 요청부터 401입니다.

아래 예제는 셸의 `MEMO_API_TOKEN` 환경변수에 사용자가 안전하게 주입한 토큰을 사용합니다. 실제 비밀 문자열을 파일·저장소에 넣거나 공유 로그에 출력하지 마세요.

```sh
curl --fail-with-body -H "Authorization: Bearer $MEMO_API_TOKEN" \
  'http://localhost:8787/api/notes?limit=40&offset=0'

curl --fail-with-body -G -H "Authorization: Bearer $MEMO_API_TOKEN" \
  --data-urlencode 'q=프로젝트 회의' --data-urlencode 'sort=newest' \
  'http://localhost:8787/api/notes'
```

브라우저는 `POST /login`의 비밀번호 인증 후 HttpOnly 세션 쿠키를 사용합니다. `GET /session`에서 받은 CSRF 값을 `X-CSRF-Token`으로 모든 변경 요청에 보냅니다. 외부 도구는 세션 쿠키 대신 Bearer 토큰을 사용하세요.

## 데이터 모델

```json
{
  "id": "메모 UUID",
  "title": "",
  "body": "첫 번째 줄\n- [ ] 확인할 일",
  "created_at": "2026-09-15T01:00:00.000000Z",
  "updated_at": "2026-09-15T01:00:00.000000Z",
  "tags": ["선택 태그"],
  "starred": false,
  "archived": false,
  "deleted": false,
  "version": 1,
  "display_title": "첫 번째 줄",
  "attachments": []
}
```

시각은 UTC ISO 8601. UI는 기기 시간대로 표시합니다. 일반 생성/수정 API에서는 ID·작성일을 변경할 수 없고 서버가 수정일과 버전을 관리합니다. 원본 날짜·버전 복원은 검증된 ZIP 가져오기를 사용합니다. 본문 최대 200만 자, 제목 500자, 태그 최대 50개(각 80자). 제목·본문은 NFC 정규화합니다.

## 메모 목록·검색

`GET /notes`

| 인수 | 설명 |
|---|---|
| `q` | 최대 300자/12개 검색어. 공백 분리 AND. 제목/본문 전체 부분 문자열. 영문 대소문자 무시 |
| `state` | `active`(기본) 또는 `all`: 보관 포함·휴지통 제외. `starred`, `archive`, `trash` |
| `sort` | `newest`(기본) 최근 수정순 또는 `oldest` 오래된 수정순. 동률은 동일 방향 ID순 |
| `from` | 시간대가 있는 ISO 8601 수정 시각, 포함 경계 |
| `to` | 시간대가 있는 ISO 8601 수정 시각, 제외 경계 |
| `tag` | 정확히 일치하는 태그 하나 |
| `limit` | 기본 40, 1~100 |
| `offset` | 기본 0, 0~1,000,000 |

응답: `{items: [...], total, offset, next_offset, terms}`. 끝 페이지는 `next_offset: null`. 각 item은 메모 메타데이터와 `display_title`, `snippet`, `thumbnail_url`을 포함하지만 `body`와 첨부 전체를 포함하지 않습니다. `display_title`·`snippet`에서 이미지 Markdown 문법은 제외합니다. `thumbnail_url`은 이 메모에 속하는 첫 본문 이미지의 인증된 `/api/attachments/{id}` 경로이며 없으면 `null`입니다. 외부 이미지나 다른 메모의 첨부를 썸네일로 사용하지 않습니다. 썸네일은 별도 파생 파일을 만들지 않고 원본 이미지 URL을 지연 로드합니다. HTML 대신 평문을 반환하므로 외부 UI가 직접 이스케이프·강조해야 합니다. 휴지통은 별도 범위로 검색됩니다.

예: 서울 시간 9월 1일~15일 전체를 조회하려면 `from=2026-09-01T00:00:00+09:00`, `to=2026-09-16T00:00:00+09:00`. URL에서 `+`를 인코딩하거나 `--data-urlencode`를 사용하세요.

## 단일 조회·작성·수정·삭제

- `GET /notes/{id}` → 200, 본문과 첨부 메타데이터 포함. 없으면 404. 선택적으로 `?known_version=5`를 전달하면 같은 버전일 때 `{id, version, unchanged: true}`만 반환합니다. 버전이 다르면 최신 본문·태그·상태·첨부를 반환하며 인증 규칙은 같습니다.
- `POST /notes` → 201. JSON의 `title`, `body`, `tags`, `starred`, `archived`, `deleted`는 생략 가능하지만 제목이나 본문에 내용이 있어야 합니다. 공백·빈 목록/체크리스트만 있으면 400입니다. `id`는 선택적 UUID. 지정한 ID가 이미 있으면 409와 `current`. 응답 유실 후 UUID 재시도로 중복 생성 방지.
- `PATCH /notes/{id}` → 200. `version` 필수. 변경할 필드만 전달 가능. 첨부 없는 메모의 제목·본문을 모두 비우는 수정은 400이며 기존 내용을 유지합니다. 기존 빈 메모의 상태 변경·휴지통 복구는 가능합니다.
- `DELETE /notes/{id}` → 200. JSON `{version}` 필수. 휴지통 이동이며 영구 삭제가 아닙니다.
- `POST /notes/trash` → 200 `{deleted: 개수}`. JSON `{items:[{id,version},...]}`로 1~1,000개를 함께 휴지통으로 이동합니다. 하나라도 버전 충돌·삭제·누락이면 409로 전체를 취소합니다.
- 복구: `PATCH /notes/{id}`에 `{version, deleted:false}`.
- `POST /notes/{id}/copy` → 201. 선택한 본문/제목/태그/상태를 새 ID로 복제하고 원본의 첨부를 새 첨부 ID로 복사해 본문 링크를 치환. 원본을 변경하지 않아 버전을 요구하지 않습니다. 충돌 초안 보존용입니다.

```sh
curl --fail-with-body -X POST -H "Authorization: Bearer $MEMO_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"body":"지금 떠오른 생각\n- [ ] 나중에 확인","tags":[]}' \
  'http://localhost:8787/api/notes'
```

수정 예제의 `NOTE_ID`는 조회 응답의 실제 ID로 설정하고 `version`도 최신 조회값으로 바꾸세요.

```sh
curl --fail-with-body -X PATCH -H "Authorization: Bearer $MEMO_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"version":1,"body":"수정한 본문"}' \
  "http://localhost:8787/api/notes/$NOTE_ID"
```

### 충돌 규칙

버전이 없으면 **428**. 서버의 현재 버전과 다르면 **409** + `{error, current: Note}`. 서버 내용을 다시 읽어 사용자가 병합하거나 별도 메모를 만들어야 합니다. 받은 최신 버전으로 자동 재전송해 덮어쓰지 마세요. 성공한 수정·첨부·휴지통 이동마다 버전이 1 증가합니다.

## 첨부

`POST /notes/{id}/attachments`: multipart `file`과 `version`. 파일당 20MB. 선택적 `offset`은 본문에서 삽입할 위치(Unicode 코드 포인트 기준, 기본은 본문 끝)입니다. 아직 저장되지 않은 메모는 새 UUID 경로에 `version=0`, `note`(메모 필드의 JSON 문자열)를 함께 전달하면 메모와 첨부를 한 트랜잭션으로 생성합니다. 실패하면 빈 메모도 남기지 않습니다. 201의 Note에 추가된 본문 링크, 새 버전, 첨부 목록을 반환합니다. 동일 이름도 새 UUID로 저장합니다. 버전 충돌 시 본문과 첨부 모두 변경하지 않습니다.

`GET /attachments/{id}`: 메모와 같은 인증 필요. 안전한 이미지 MIME은 inline, 나머지는 `Content-Disposition: attachment`, `nosniff`, sandbox CSP로 전달합니다.

## 소유자 웹 세션 전용

| 경로 | 기능 |
|---|---|
| `POST /login` | `{password, remember?:true}` → `{csrf, expires, remember}`, 세션 쿠키 발급 |
| `GET /session` | `{csrf, instance, session_id, expires, reauth_until}` |
| `POST /logout` | 현재 세션 폐기 |
| `POST /password` | `{password}`; 12~1024자, 최근 본인 확인 필요, 모든 웹 세션 만료 |
| `GET /tokens` | 이름·ID·권한·발급일 목록; 비밀 문자열/해시 제외 |
| `POST /tokens` | `{name, scope}` → `{id, token}` (한 번 표시) |
| `DELETE /tokens/{id}` | 토큰 폐기 |
| `GET /export` | v1 전체 ZIP 다운로드 |
| `POST /import/preview` | multipart `file` → 추가·건너뛰기·첨부 개수, 정책, 샘플, `preview_id` |
| `POST /import/commit` | `{preview_id}` → `{created, skipped}`; 만료 시 410 |

## 오류

JSON `{error: "한국어 안내"}`. 400 잘못된 입력/ZIP, 401 인증 누락·만료, 403 권한/CSRF/Origin, 404 없음, 409 충돌, 410 가져오기 만료, 413 크기 초과, 428 버전 누락 또는 본인 확인 필요, 429 로그인 요청 제한, 503 저장·DB 오류. 요청 실패 시 기존 데이터는 트랜잭션 범위에서 유지됩니다. 전송 중 연결이 끊기면 서버가 이미 저장했을 수 있으므로 ID와 최신 버전을 조회해 확인하세요.

이 API는 후속 MCP 서버나 자동화 도구의 기반입니다. 현재 MCP 서버 또는 ChatGPT 계정 연결은 구현하지 않았습니다.


## 브라우저 인증 API

경로는 모두 `/api` 기준입니다. 패스키·세션 관리·재인증은 소유자 쿠키 전용이며 Bearer 토큰으로 접근할 수 없습니다. 예외는 공개 로그인 경로와 `/auth/config`입니다. 인증 API의 JSON 요청 크기는 최대 64KB입니다. 시각 숫자는 Unix 초입니다.

| 경로 | 입력/응답 |
|---|---|
| `GET /auth/config` | 공개. `{passkey_origin, passkeys_available, remember_days:30}` |
| `POST /reauth/password` | `{password}` → `{csrf, reauthenticated:true}`; 쿠키 교체 |
| `GET /sessions` | `{items:[{id,device_name,created_at,last_seen,expires,remember,current}]}` |
| `DELETE /sessions/{id}` | 해당 웹 세션 해제 → `{ok,current}` |
| `POST /sessions/revoke-others` | 현재 세션을 제외한 모든 웹 세션 해제 |
| `GET /passkeys` | `{items:[{id,name,rp_id,created_at,last_used}],origin}` |
| `DELETE /passkeys/{id}` | 키 및 해당 키로 로그인한 세션 폐기 → `{ok,current}` |
| `POST /passkeys/register/options` | `{}` → `{challenge_id,options}`; 최근 본인 확인 필요 |
| `POST /passkeys/register/verify` | `{challenge_id,response,name?}` → 201 `{id,registered:true}` |
| `POST /passkeys/login/options` | 공개. `{remember?:true}` → `{challenge_id,options}` 및 임시 흐름 쿠키 |
| `POST /passkeys/login/verify` | 공개. `{challenge_id,response}` → `{csrf,expires,remember}` 및 로그인 쿠키 |
| `POST /passkeys/reauth/options` | `{}` → `{challenge_id,options}` |
| `POST /passkeys/reauth/verify` | `{challenge_id,response}` → `{csrf,reauthenticated:true}` 및 교체 쿠키 |

모든 패스키 POST에는 정확히 설정된 `Origin`과 `X-Passkey-Request: 1`이 필요합니다. 로그인용 공개 경로를 제외하면 `X-CSRF-Token`도 필요합니다. `options`의 base64url 문자열 필드를 바이너리로 변환해 `navigator.credentials.create/get`에 전달하고, 결과를 WebAuthn JSON(base64url)으로 직렬화해 `response`에 보냅니다. 이 과정을 흉내 낸 HTTP 호출만으로 생체 인증을 완료할 수 없습니다. 실제 UI 예시는 `static/auth-ui.js`에 있습니다.

`remember:true`(기본)는 로그인 시점부터 최대 30일이며 자동 연장하지 않습니다. `false`는 세션 쿠키와 서버 최대 12시간입니다. `expires`/`reauth_until`은 Unix 초입니다.

ZIP 내보내기·가져오기, 비밀번호 변경, 토큰/세션 변경, 패스키 등록/삭제는 최근 5분 이내 인증이 필요합니다. 오래된 세션은 HTTP **428**과 `{code:"REAUTH_REQUIRED",error:"…"}`를 받습니다. UI는 패스키 또는 `/reauth/password`로 확인한 후 원래 요청을 한 번 재시도합니다. 사용자가 취소하면 원래 작업을 실행하지 않습니다. 메모의 버전 누락 428에는 이 코드가 없으므로 구분하세요. 재인증은 쿠키를 교체하지만 CSRF와 절대 만료일을 유지합니다.

잘못된 서명/사용자 확인은 401, 등록 검증 실패는 400, 만료·재사용 challenge는 409, 인증 요청 과다/비밀번호 시도 제한은 429입니다. `device_name`은 브라우저가 보낸 정보를 사람이 구분하기 위한 표시로만 사용합니다.

## 폴더

- `GET /api/folders`: `items`에 `id`, `name`, `version`, `count`, 응답의 `unfiled`에 미분류 개수를 반환합니다. 개수는 보관된 메모를 포함하고 휴지통을 제외합니다.
- `POST /api/folders`: `{"name":"여행"}` (1~80자). 생성된 ID를 반환합니다.
- `PATCH /api/folders/{id}`: `{"name":"여행 계획","version":1}`. 오래된 버전은 409입니다.
- 메모 생성·수정·복사에 `folder_id`를 지정합니다. `null`은 폴더 없음, UUID는 존재하는 폴더입니다. 수정은 기존의 `version` 충돌 검사를 적용합니다.
- `GET /api/notes?folder_id=<UUID>`로 폴더별 조회, `folder_id=none`으로 미분류 조회가 가능합니다. 생략하면 모든 폴더를 조회합니다. 검색·날짜·상태 필터와 함께 사용할 수 있습니다.
- 폴더 API도 인증이 필요하며 쓰기 작업에는 쓰기 토큰 또는 CSRF가 있는 세션이 필요합니다.
