# backend/app/api/admin_api.py

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Body
from typing import List, Optional
from ..core.database import SessionLocal
from ..models.models import LessonBackup
import os, shutil

# services 폴더에서 파이프라인 함수 임포트
from ..services import content_pipeline_service

router = APIRouter()

@router.post("/admin/generate-all-content", tags=["Admin"])
def trigger_full_content_generation(background_tasks: BackgroundTasks):
    """
    [관리자용] 모든 레벨의 학습 콘텐츠를 처음부터 다시 생성합니다.
    이 작업은 백그라운드에서 실행되며, 완료까지 시간이 오래 걸릴 수 있습니다.
    """
    print("관리자 요청: 전체 콘텐츠 생성 파이프라인을 백그라운드에서 시작합니다.")
    
    # 시간이 매우 오래 걸리는 작업을 백그라운드 태스크로 등록
    background_tasks.add_task(content_pipeline_service.run_full_content_generation)
    
    return {"message": "전체 콘텐츠 생성 작업이 백그라운드에서 시작되었습니다. 서버 로그를 확인하여 진행 상황을 모니터링하세요."}

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
        # 경로 설정
        OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))
        BACKUP_DIR = os.path.join(OUTPUT_DIR, 'backup')
        src_backup_path = os.path.join(BACKUP_DIR, backup.backup_filename)
        target_path = os.path.join(OUTPUT_DIR, backup.lesson_filename)
        # 복원 전 현재 파일도 백업
        if os.path.exists(target_path):
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            new_backup_filename = f"{backup.lesson_filename.replace('.json', '')}_restore_{timestamp}.json"
            new_backup_path = os.path.join(BACKUP_DIR, new_backup_filename)
            shutil.copy2(target_path, new_backup_path)
            db.add(LessonBackup(
                lesson_filename=backup.lesson_filename,
                backup_filename=new_backup_filename,
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
    import traceback
    print("[LOG] backup-list 라우트 진입")  # 함수 진입 로그
    try:
        # generated_content 폴더가 learnsphere-api보다 상위에 있어도 동작하도록 경로 계산
        OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))
        BACKUP_DIR = os.path.join(OUTPUT_DIR, 'backup')
        result = {}
        print("[LOG] 백업 폴더 경로:", BACKUP_DIR)
        if not os.path.exists(BACKUP_DIR):
            print("[LOG] 백업 폴더가 존재하지 않습니다.")
            return result
        found_any = False
        for date_folder in sorted(os.listdir(BACKUP_DIR)):
            date_path = os.path.join(BACKUP_DIR, date_folder)
            print("[LOG] 폴더/파일:", date_folder, "| 경로:", date_path)
            if not os.path.isdir(date_path):
                print("[LOG] 폴더가 아님:", date_path)
                continue
            files = [f for f in os.listdir(date_path) if f.endswith('.json')]
            print("[LOG]   - json 파일 목록:", files)
            result[date_folder] = files
            found_any = True
        if not found_any:
            print("[LOG] backup 폴더 내에 날짜별 폴더가 없거나, 모든 폴더가 비어 있음")
        print("[LOG] 최종 반환값:", result)
        return result
    except Exception as e:
        print("[ERROR] backup-list 라우트에서 예외 발생!")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/restore-backup-date", tags=["Admin"])
def restore_backup_date(date: str = Body(..., embed=True)):
    """
    특정 날짜 폴더의 모든 백업 파일을 generated_content 최상위로 복원(덮어쓰기)
    """
    import shutil
    OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))
    BACKUP_DIR = os.path.join(OUTPUT_DIR, 'backup')
    date_path = os.path.join(BACKUP_DIR, date)
    if not os.path.exists(date_path):
        raise HTTPException(status_code=404, detail="해당 날짜 폴더가 없습니다.")
    restored_files = []
    for fname in os.listdir(date_path):
        if not fname.endswith('.json'):
            continue
        src = os.path.join(date_path, fname)
        dst = os.path.join(OUTPUT_DIR, fname)
        shutil.copy2(src, dst)
        restored_files.append(fname)
    return {"restored": restored_files, "message": f"{date}의 모든 백업 파일을 복원했습니다."}
