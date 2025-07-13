# backend/app/api/admin_api.py

from fastapi import APIRouter, BackgroundTasks, HTTPException

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
