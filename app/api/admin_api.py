# backend/app/api/admin_api.py

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import os, re, shutil

from ..core.database import SessionLocal, get_db
from ..core.security import verify_admin_key
from ..crud import crud_lessons
from ..models.models import LessonBackup

# services 폴더에서 파이프라인 함수 임포트
from ..services import content_pipeline_service

# 모든 관리자 엔드포인트는 X-Admin-API-Key 헤더 인증을 요구합니다.
router = APIRouter(dependencies=[Depends(verify_admin_key)])

# generated_content 폴더가 learnsphere-api보다 상위에 있어도 동작하도록 경로 계산
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))
BACKUP_DIR = os.path.join(OUTPUT_DIR, 'backup')


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


@router.get("/admin/lesson-backups", tags=["Admin"])
def get_lesson_backups(lesson_filename: str):
    """
    특정 레슨 파일의 백업 목록을 조회합니다.
    """
    db = SessionLocal()
    try:
        backups = db.query(LessonBackup).filter(LessonBackup.lesson_filename == lesson_filename).order_by(LessonBackup.created_at.desc()).all()
        return [
            {
                "id": b.id,
                "lesson_filename": b.lesson_filename,
                "backup_filename": b.backup_filename,
                "created_at": b.created_at,
                "created_by": b.created_by,
                "action": b.action
            } for b in backups
        ]
    finally:
        db.close()


@router.post("/admin/restore-lesson-backup", tags=["Admin"])
def restore_lesson_backup(backup_id: int = Body(..., embed=True), restored_by: Optional[str] = Body(None, embed=True)):
    """
    선택한 백업 파일로 레슨 파일을 복원합니다. 복원 전 현재 파일도 백업합니다.
    """
    db = SessionLocal()
    try:
        backup = db.query(LessonBackup).filter(LessonBackup.id == backup_id).first()
        if not backup:
            raise HTTPException(status_code=404, detail="해당 백업을 찾을 수 없습니다.")
        src_backup_path = os.path.join(BACKUP_DIR, backup.backup_filename)
        if not os.path.exists(src_backup_path):
            raise HTTPException(status_code=404, detail=f"백업 파일이 존재하지 않습니다: {backup.backup_filename}")
        target_path = os.path.join(OUTPUT_DIR, backup.lesson_filename)
        # 복원 전 현재 파일도 백업 (생성 파이프라인과 동일하게 날짜 폴더에 저장)
        if os.path.exists(target_path):
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            dated_backup_dir = os.path.join(BACKUP_DIR, today_str)
            os.makedirs(dated_backup_dir, exist_ok=True)
            timestamp = now.strftime('%Y%m%d_%H%M%S')
            new_backup_filename = f"{backup.lesson_filename.replace('.json', '')}_restore_{timestamp}.json"
            new_backup_path = os.path.join(dated_backup_dir, new_backup_filename)
            shutil.copy2(target_path, new_backup_path)
            db.add(LessonBackup(
                lesson_filename=backup.lesson_filename,
                backup_filename=f"{today_str}/{new_backup_filename}",
                created_by=restored_by,
                action='backup-before-restore'
            ))
            db.commit()
        # 복원
        shutil.copy2(src_backup_path, target_path)
        db.add(LessonBackup(
            lesson_filename=backup.lesson_filename,
            backup_filename=backup.backup_filename,
            created_by=restored_by,
            action='restore'
        ))
        db.commit()
        return {"message": f"{backup.lesson_filename} 파일이 {backup.backup_filename} 백업본으로 복원되었습니다."}
    finally:
        db.close()


@router.get("/admin/backup-list", tags=["Admin"])
def get_backup_list():
    """
    backup/ 하위의 날짜별 폴더와 각 폴더의 백업 파일 목록을 반환합니다.
    """
    try:
        result = {}
        if not os.path.exists(BACKUP_DIR):
            return result
        for date_folder in sorted(os.listdir(BACKUP_DIR)):
            date_path = os.path.join(BACKUP_DIR, date_folder)
            if not os.path.isdir(date_path):
                continue
            result[date_folder] = [f for f in os.listdir(date_path) if f.endswith('.json')]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/restore-backup-date", tags=["Admin"])
def restore_backup_date(date: str = Body(..., embed=True)):
    """
    특정 날짜 폴더의 모든 백업 파일을 generated_content 최상위로 복원(덮어쓰기)
    """
    # 날짜 값에 경로 구분자가 섞여 들어오는 것을 방지
    if os.path.basename(date) != date:
        raise HTTPException(status_code=400, detail="유효하지 않은 날짜 형식입니다.")
    date_path = os.path.join(BACKUP_DIR, date)
    if not os.path.exists(date_path):
        raise HTTPException(status_code=404, detail="해당 날짜 폴더가 없습니다.")
    restored_files = []
    for fname in os.listdir(date_path):
        if not fname.endswith('.json'):
            continue
        src = os.path.join(date_path, fname)
        # 백업 파일명의 타임스탬프 접미사를 제거해 원본 레슨 파일명으로 복원
        original_name = re.sub(r'(_restore)?_\d{8}_\d{6}\.json$', '.json', fname)
        dst = os.path.join(OUTPUT_DIR, original_name)
        shutil.copy2(src, dst)
        restored_files.append(original_name)
    return {"restored": restored_files, "message": f"{date}의 모든 백업 파일을 복원했습니다."}
