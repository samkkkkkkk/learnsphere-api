# backend/app/api/admin_api.py

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from typing import Optional

from ..core.database import get_db
from ..core.security import verify_admin_key
from ..crud import crud_lessons

# services 폴더에서 파이프라인 함수 임포트
from ..services import content_pipeline_service

# 모든 관리자 엔드포인트는 X-Admin-API-Key 헤더 인증을 요구합니다.
router = APIRouter(dependencies=[Depends(verify_admin_key)])


def _generation_summary(generation) -> dict:
    return {
        "id": generation.id,
        "source": generation.source,
        "status": generation.status,
        "created_by": generation.created_by,
        "started_at": generation.started_at,
        "completed_at": generation.completed_at,
        "total_topics": generation.total_topics,
        "succeeded": generation.succeeded,
        "failed_count": len(generation.failed_topics or []),
    }


@router.post("/admin/generate-all-content", tags=["Admin"])
def trigger_full_content_generation(background_tasks: BackgroundTasks,
                                    db: Session = Depends(get_db)):
    """
    [관리자용] 모든 레벨의 학습 콘텐츠를 처음부터 다시 생성합니다.
    이 작업은 백그라운드에서 실행되며, 완료까지 시간이 오래 걸릴 수 있습니다.
    진행 중에도 사용자는 이전 세대의 레슨을 그대로 조회합니다.
    """
    generation = content_pipeline_service.request_full_generation(db, created_by='admin')
    if generation is None:
        raise HTTPException(status_code=409, detail="이미 실행 중인 생성 작업이 있습니다.")

    print(f"관리자 요청: 전체 콘텐츠 생성 파이프라인을 백그라운드에서 시작합니다. (generation {generation.id})")
    background_tasks.add_task(
        content_pipeline_service.run_full_content_generation, generation.id)

    return {
        "message": "전체 콘텐츠 생성 작업이 백그라운드에서 시작되었습니다. 서버 로그를 확인하여 진행 상황을 모니터링하세요.",
        "generation_id": generation.id,
    }


# --- 세대(generation) 관리 ---

@router.get("/admin/generations", tags=["Admin"])
def list_generations(db: Session = Depends(get_db)):
    """생성 세대 목록을 최신순으로 반환합니다."""
    return [_generation_summary(g) for g in crud_lessons.get_generations(db)]


@router.get("/admin/generations/{generation_id}", tags=["Admin"])
def get_generation_detail(generation_id: int, db: Session = Depends(get_db)):
    """세대 상세 (실패 토픽 목록 포함)."""
    generation = crud_lessons.get_generation(db, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="해당 세대를 찾을 수 없습니다.")
    detail = _generation_summary(generation)
    detail["failed_topics"] = generation.failed_topics or []
    detail["prompt"] = generation.prompt
    detail["params"] = generation.params
    return detail


@router.post("/admin/generations/{generation_id}/activate", tags=["Admin"])
def activate_generation(generation_id: int, db: Session = Depends(get_db)):
    """
    특정 세대의 버전 전체를 활성으로 일괄 전환합니다.
    (구 restore-backup-date의 대체 — 날짜 폴더 복원 대신 세대 단위 전환)
    """
    try:
        generation = crud_lessons.activate_generation(db, generation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if generation is None:
        raise HTTPException(status_code=404, detail="해당 세대를 찾을 수 없습니다.")
    return {"message": f"generation {generation_id}의 레슨으로 전환했습니다."}


# --- 레슨 버전 관리 ---

@router.get("/admin/lessons/{lesson_id}/versions", tags=["Admin"])
def list_lesson_versions(lesson_id: int, db: Session = Depends(get_db)):
    """
    특정 레슨의 전체 버전 목록을 최신순으로 반환합니다.
    (구 lesson-backups의 대체 — 파일 백업 대신 불변 버전)
    """
    versions = crud_lessons.get_versions(db, lesson_id)
    if not versions:
        raise HTTPException(status_code=404, detail="해당 레슨의 버전이 없습니다.")
    return [
        {
            "version_id": v.id,
            "generation_id": v.generation_id,
            "title": v.title,
            "created_at": v.created_at,
            "is_current": v.is_current,
            "source": v.generation.source if v.generation else None,
        } for v in versions
    ]


@router.post("/admin/lessons/{lesson_id}/restore", tags=["Admin"])
def restore_lesson_version(lesson_id: int,
                           version_id: int = Body(..., embed=True),
                           restored_by: Optional[str] = Body(None, embed=True),
                           db: Session = Depends(get_db)):
    """
    선택한 버전을 레슨의 활성 버전으로 전환합니다.
    (구 restore-lesson-backup의 대체 — 버전은 불변이라 '복원 전 백업'이 필요 없습니다)
    """
    version = crud_lessons.restore_version(db, lesson_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="해당 레슨의 버전을 찾을 수 없습니다.")
    if restored_by:
        print(f"레슨 {lesson_id} 버전 {version_id} 복원 (by {restored_by})")
    return {"message": f"레슨 {lesson_id}이(가) 버전 {version_id}(으)로 복원되었습니다."}
