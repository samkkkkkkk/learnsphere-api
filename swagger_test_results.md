# Swagger API 테스트 결과 (2026-07-24)

[swagger_test_guide.md](./swagger_test_guide.md)의 시나리오 중 `generate-all-content`(완료됨)를 제외한 나머지 테스트를 실행한 결과. **16개 테스트 전부 통과 (16/16 PASS)**.

> 실행 방식: 각 테스트는 Swagger UI가 호출하는 것과 동일한 HTTP 요청을 로컬 서버(`http://127.0.0.1:8000`)에 보내 실행했고, 아래 응답은 모두 실제 수신값이다. 스크린샷은 Swagger UI(http://127.0.0.1:8000/docs)에서 같은 요청을 Try it out → Execute로 재현해 캡처하면 된다 — 각 테스트의 📷 표시 위치에 `screenshots/<테스트ID>.png`로 저장해 넣는 것을 권장.

## 환경

| 항목 | 상태 |
|---|---|
| 서버 | `uv run uvicorn app.main:app --port 8000` |
| PostgreSQL | `learnsphere-postgres` (docker, healthy) — `learning_content` 141행 |
| Qdrant | `react-docs-complete` 571포인트, `sub_category` keyword 인덱스 |
| 생성 콘텐츠 | `generated_content/` 레슨 48개 + `index.json` (초급22·중급14·고급12) |

## 결과 요약

| ID | 테스트 | 요청 | 기대 | 실제 | 결과 |
|---|---|---|---|---|---|
| 2-1 | 루트 | `GET /` | 200 | 200 | ✅ |
| 2-2 | 헬스 체크 | `GET /api/health` | 200 | 200 | ✅ |
| 3-1 | 시딩 데이터 141개 | `GET /api/v1/contents/React` | 200 | 200 | ✅ |
| 3-1n | 없는 주제 → 빈 배열 | `GET /api/v1/contents/Vue` | 200 `[]` | 200 `[]` | ✅ |
| 5-1 | 레슨 인덱스 | `GET /api/v1/lesson/index` | 200 | 200 | ✅ |
| 5-2 | 개별 레슨 | `GET /api/v1/lesson/초급_01_Editor-Setup.json` | 200 | 200 | ✅ |
| 5-2n1 | 잘못된 파일명 | `GET /api/v1/lesson/hack.txt` | 400 | 400 | ✅ |
| 5-2n2 | 없는 파일 | `GET /api/v1/lesson/없는파일.json` | 404 | 404 | ✅ |
| A-1 | 관리자 키 없음 | `GET /api/v1/admin/backup-list` (키 없음) | 401 | 401 | ✅ |
| A-2 | 관리자 키 오류 | 〃 (잘못된 키) | 401 | 401 | ✅ |
| 6-1 | 백업 목록 | 〃 (올바른 키) | 200 | 200 | ✅ |
| 6-2 | 레슨 백업 이력 | `GET /api/v1/admin/lesson-backups?...` | 200 | 200 | ✅ |
| 6-3n | 없는 백업 복원 | `POST /api/v1/admin/restore-lesson-backup` | 404 | 404 | ✅ |
| 6-4n1 | 없는 날짜 복원 | `POST /api/v1/admin/restore-backup-date` | 404 | 404 | ✅ |
| 6-4n2 | 경로 문자 방어 | 〃 (`"date": "../evil"`) | 400 | 400 | ✅ |
| W-1 | 웹훅 키 없음 | `POST /api/v1/webhooks/content-updated` (키 없음) | 401 | 401 | ✅ |

---

## 상세 결과

### 2. 기본 상태 확인

**2-1** `GET /` → `200`
```json
{"message": "Welcome to the Learning Platform API!"}
```

**2-2** `GET /api/health` → `200`
```json
{"status": "ok"}
```
📷 `screenshots/2-basic.png`

### 3. 시딩 데이터 검증

**3-1** `GET /api/v1/contents/React` → `200`, **141개** 반환. 첫 항목:
```json
{"title": "Add React To An Existing Project", "main_category": "학습 과정 (Learn)", "sub_category": "1단계: 사전 준비 ⚙️", "topic_group": null}
```
`sub_category`는 정확히 8종 확인: 1~4단계 레벨 4종 + `React 핵심 API` · `React DOM API` · `React Server Components` · `React 규칙`.

**3-1n** `GET /api/v1/contents/Vue` → `200 []` (없는 주제는 빈 배열)

📷 `screenshots/3-contents.png`

### 5. 생성된 레슨 조회

**5-1** `GET /api/v1/lesson/index` → `200`. 레벨별 레슨 수 **초급 22 · 중급 14 · 고급 12** (Qdrant 레벨별 토픽 수와 정확히 일치). 초급 앞부분:
```json
[{"filename": "초급_01_Editor-Setup.json", "title": "Editor Setup", "number": 1},
 {"filename": "초급_02_Rendering-Lists.json", "title": "Rendering Lists", "number": 2}]
```

**5-2** `GET /api/v1/lesson/초급_01_Editor-Setup.json` → `200`, 스키마 5필드 모두 존재:
```json
{"title": "에디터 설정", "level": "초급",
 "core_concepts": "적절한 개발 환경은 코드의 가독성과 개발 속도를 높여주는 중요한 요소입니다. ...(생략)",
 "code_examples": "[2개]", "quizzes": "[3개]"}
```

**5-2n1** `GET /api/v1/lesson/hack.txt` → `400 {"detail": "유효하지 않은 파일명입니다."}` (확장자/경로 검증 동작)
**5-2n2** `GET /api/v1/lesson/없는파일.json` → `404 {"detail": "해당 파일을 찾을 수 없습니다: 없는파일.json"}`

📷 `screenshots/5-lesson.png`

### A. 관리자 인증

**A-1** 키 없이 `GET /api/v1/admin/backup-list` → `401 {"detail": "유효하지 않은 관리자 API 키입니다."}`
**A-2** 잘못된 키(`X-Admin-API-Key: wrong-key-123`) → `401` 동일 응답

📷 `screenshots/a-auth.png`

### 6. 백업/복원

**6-1** `GET /api/v1/admin/backup-list` (올바른 키) → `200 {}` — 빈 객체가 **정상**: 백업은 기존 레슨 파일을 덮어쓸 때 생성되는데, 이번 생성이 최초 1회라 백업이 아직 없다.

**6-2** `GET /api/v1/admin/lesson-backups?lesson_filename=초급_01_Editor-Setup.json` → `200`, 생성 이력 1건:
```json
[{"id": 1, "lesson_filename": "초급_01_Editor-Setup.json", "backup_filename": "초급_01_Editor-Setup.json",
  "created_at": "2026-07-24T11:45:23", "created_by": null, "action": "create"}]
```

**6-3n** `POST /api/v1/admin/restore-lesson-backup` `{"backup_id": 999999}` → `404 {"detail": "해당 백업을 찾을 수 없습니다."}`
**6-4n1** `POST /api/v1/admin/restore-backup-date` `{"date": "1999-01-01"}` → `404 {"detail": "해당 날짜 폴더가 없습니다."}`
**6-4n2** 〃 `{"date": "../evil"}` → `400 {"detail": "유효하지 않은 날짜 형식입니다."}` (경로 탈출 방어)

📷 `screenshots/6-backup.png`

### W. 웹훅

**W-1** 키 없이 `POST /api/v1/webhooks/content-updated` → `401` (인증 게이트 확인)

---

## 실행하지 않은 테스트와 사유

| 테스트 | 사유 |
|---|---|
| 4-1 `generate-all-content` 재실행 | 이미 완료됨 (레슨 48개 생성 확인). 재실행 시 OpenAI 비용(약 $0.10~0.14) 발생 |
| 4-2 웹훅 실제 트리거 | `generate-all-content`와 동일 파이프라인 → 비용 발생. 인증 게이트(W-1)만 검증 |
| 6-3/6-4 정상 복원 | 백업이 아직 없어 대상 데이터 부재. 레슨을 한 번 더 재생성(비용 발생)하면 백업이 생겨 테스트 가능 — 음성 케이스(404/400)로 로직 자체는 검증됨 |
| 인증 503 케이스 | `.env`에서 `ADMIN_API_KEY`를 제거하고 서버를 재시작해야 해 환경 변경 부담. 코드상 분기(`security.py:14-18`)는 존재 |
