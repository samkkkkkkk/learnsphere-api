# 레슨 저장소 DB 이관 — 완료 보고 (2026-07-24)

> `generated_content/` 파일 기반 레슨 저장소를 PostgreSQL 세대/버전 모델로 이관한 결과 보고.
> 관련 문서: [DB_MIGRATION_PLAN.md](./DB_MIGRATION_PLAN.md)(설계) · [db_detail.md](./db_detail.md)(Phase 계획) · [detail_tasks.md](./detail_tasks.md)(체크리스트)

## 결과 요약

**Phase 0~7 전체 완료.** 레슨 본문은 이제 PostgreSQL(`lessons`/`lesson_versions`)에 세대(generation) 단위로 저장되고, 프론트엔드는 ID 기반 API로 조회한다. 재생성은 세대 단위로 원자적으로 전환되며(진행 중에는 이전 세대 서빙), 복원은 파일 복사가 아닌 불변 버전 간 `is_current` 이동이라 데이터 손실 없이 왕복 가능하다.

## Phase별 커밋

### learnsphere-api (`feature/lesson-db-migration`)

| Phase | 커밋 | 내용 |
|---|---|---|
| 0 | `ace0622` | 계획 문서 3종 + 사전 정리 (선행 커밋 `7b694fb`, `18d5e35`, `2411375`) |
| 1 | `bcfc566` | alembic 도입, `0001_baseline`, main.py의 `create_all` 제거 |
| 2 | `26724b6` | 세대/버전 모델 3종 + `0002` 마이그레이션 + 스키마/CRUD + 테스트 인프라(in-memory SQLite) |
| 3 | `28b1aa0` | `GET /api/v1/lessons`·`/lessons/{id}` 신설 + import 스크립트로 실데이터 48개 적재 |
| 4 | `187315f` | 생성 파이프라인 DB 전환 — 세대 원자 전환, 생성 시점 스키마 검증, 중복 실행 409 가드 |
| 5 | `56757df` | 관리자 세대/버전 API 6종 신설, 구 파일 백업 엔드포인트 4종 제거 |
| 7 | `3aa8bde` | 구 `/lesson/*` API·`/static/content` 마운트·dead 스크립트 제거, 문서 갱신 |

### learnsphere-frontend (`feature/lesson-db-migration`)

| Phase | 커밋 | 내용 |
|---|---|---|
| 6 | `2d9fc53` | ID 기반 API 전환, 관리자 키 입력 UI + `X-Admin-API-Key` 자동 첨부 인터셉터(401 버그 해소), 세대/버전 관리 패널 |

## 검증 결과

| 항목 | 결과 |
|---|---|
| 백엔드 테스트 | pytest **60개 전부 통과** (기존 enrichment 26 + 신규 레슨 DB 34) |
| 프론트 빌드 | `npm run build` (tsc -b + vite) 통과 |
| 데이터 적재 | 초급 22 · 중급 14 · 고급 12 = 48개, is_current 버전 48개 |
| 원본 대조 | `초급_01_Editor-Setup` 원본 JSON과 API 응답 **필드 완전 일치** (explanation 포함) |
| 버전 복원 | 실 서버에서 구버전 복원 → 재복원 왕복 성공 (원상 복귀 확인) |
| 세대 전환 | activate로 generation 1 ↔ 2 왕복 성공 |
| 구 API 제거 | `/api/v1/lesson/index` 404, `/static/content/*` 404, 신 `/api/v1/lessons` 200 |
| 프록시 연동 | Vite dev 프록시 경유 `GET /api/v1/lessons` 200 |
| 인증 | admin 키 없이 401, 키 포함 200 (테스트 + 실 서버) |

## 진행 중 발견·해결한 이슈

1. **퀴즈 `explanation` 필드 유실**: 원본 파일 33건의 퀴즈에 해설 필드가 있었는데 초기 스키마에 없어 import 시 버려짐 → `Quiz.explanation` Optional 추가 + `model_dump(exclude_none=True)` 저장 + `--force` 재이관으로 해결. 프론트에 해설 표시도 추가.
2. **에러-레슨 삼킴 제거**: LLM 실패 시 오류 메시지를 본문에 담아 정상 저장하던 로직을 `LessonGenerationError` + 저장 전 검증으로 교체 — 에러 텍스트가 정식 버전으로 영구 저장되는 경로 차단.
3. **`react_complete_learning_data.json` 상태 확인**: 저장소에 존재(141개 문서, 가공 파이프라인 산출물, 커밋 `a8fe819`). ARCHITECTURE.md의 낡은 "누락" 경고를 최신화.
4. **과거 위치 복사본 정황**: pytest 캐시 경로에 `C:\WorkSpace\learnsphere-api`(구 위치)가 노출됨 — stale `__pycache__` 또는 프로젝트 복사본이 남아있을 가능성. 오늘 생성물이 `C:\WorkSpace\generated_content`에 있던 원인과 부합.

## 운영 변경 사항

- **기동 절차**: 서버 시작 전 `uv run alembic upgrade head` 필수 (create_all 자동 생성 제거). 기존 DB는 최초 1회 `alembic stamp 0001` 후 upgrade.
- **레슨 데이터는 DB에만 존재**: `docker compose down -v` 시 레슨 전체 소실 (재생성 = OpenAI 비용). **`pg_dump` 정기 백업 권장.**
- **관리자 기능**: AdminPanel 상단에 관리자 키를 입력·저장해야 생성/전환/복원 버튼이 활성화됨 (sessionStorage 보관).

## 남은 항목

- [ ] **브라우저 수동 e2e**: 학습 페이지 렌더링·레벨 전환, AdminPanel 키 입력 → 생성/세대 전환/버전 복원 클릭 확인 (`detail_tasks.md` Phase 6/7 미완 체크 항목)
- [ ] **`C:\WorkSpace\generated_content` 아카이브 처리 방침**: 현재 그대로 보존 중, 코드 참조 없음 — 보관 위치/삭제 여부는 사용자 판단
- [ ] **`C:\WorkSpace\learnsphere-api` 구 위치 복사본 확인·정리** (실재 여부 확인 필요)
- [ ] `lesson_backups` deprecated 테이블 drop 시점 결정 (추후)
- [ ] `pg_dump` 정기 백업 절차 마련 (추후)
