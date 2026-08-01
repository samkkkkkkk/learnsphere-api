# backend/app/services/content_pipeline_service.py
"""레슨 생성 파이프라인 — DB(lessons/lesson_versions) 기반.

세대(generation) 단위로 버전을 적재(is_current=False)한 뒤 finalize에서
단일 트랜잭션으로 활성 전환한다. 진행 중에는 사용자에게 이전 세대가 그대로 서빙되고,
실패한 토픽은 이전 버전을 유지한 채 failed_topics로 기록된다 (부분 성공 허용).
"""
from . import qdrant_service, openai_service
from .openai_service import LessonGenerationError
from ..core.database import SessionLocal
from ..crud import crud_lessons

LEVELS = ["초급", "중급", "고급"]


def request_full_generation(db, created_by: str = None):
    """새 세대를 생성해 반환. 이미 실행 중(running)인 세대가 있으면 None."""
    if crud_lessons.get_running_generation(db):
        return None
    return crud_lessons.create_generation(db, source='pipeline', created_by=created_by)


def run_content_generation_for_level(db, generation_id: int, level: str,
                                     failed_topics: list) -> int:
    """한 레벨의 토픽들을 생성·적재. 성공 수를 반환하고 실패는 failed_topics에 누적."""
    print(f"✅ [Pipeline-START] '{level}' 레벨의 콘텐츠 생성을 시작합니다.")
    topics_with_contexts = qdrant_service.get_contexts_by_level(level)
    if not topics_with_contexts:
        print(f"⚠️ [Pipeline-WARN] '{level}' 레벨에 해당하는 토픽이 없습니다.")
        return 0

    succeeded = 0
    total = len(topics_with_contexts)
    for position, (topic, context) in enumerate(topics_with_contexts.items(), 1):
        print(f"\n--- [Processing {position}/{total}] '{topic}' 레슨 생성 중 ---")
        try:
            content = openai_service.generate_lesson_with_llm(level, topic, context)
        except LessonGenerationError as exc:
            print(f"  > [FAIL] {exc}")
            failed_topics.append({"level": level, "topic": topic, "error": str(exc)})
            continue
        lesson = crud_lessons.upsert_lesson(db, level, crud_lessons.slugify(topic), topic)
        crud_lessons.insert_version(db, lesson, generation_id, content, position=position)
        db.commit()  # 레슨 단위 커밋 — is_current=False라 사용자에게 노출되지 않음
        succeeded += 1
        print(f"--- [Saved] '{level}' {position:02d} '{topic}' 버전 적재 완료 ---")

    print(f"✅ [Pipeline-END] '{level}' 레벨 완료 ({succeeded}/{total}, 실패 {total - succeeded})")
    return succeeded


def run_full_content_generation(generation_id: int):
    """[관리자용] 전체 레벨(초급/중급/고급) 생성.

    세대 행은 호출자(API 핸들러)가 미리 만들어 id를 전달한다.
    BackgroundTask는 요청 스코프 밖이므로 세션을 직접 생성한다.
    """
    print(f"🚀 [ADMIN-TASK] 전체 학습 콘텐츠 생성을 시작합니다. (generation {generation_id})")
    db = SessionLocal()
    try:
        failed_topics = []
        for level in LEVELS:
            run_content_generation_for_level(db, generation_id, level, failed_topics)
        crud_lessons.finalize_generation(db, generation_id, failed_topics=failed_topics)
        print(f"✅ [ADMIN-TASK] 전체 학습 콘텐츠 생성 완료. (실패 {len(failed_topics)}건)")
    except Exception as exc:
        print(f"❌ [ADMIN-TASK] 파이프라인 실행 중 오류: {exc}")
        db.rollback()
        crud_lessons.fail_generation(db, generation_id, error=str(exc))
    finally:
        db.close()
