# app/api/documents_api.py
"""관리자용 문서 업로드/관리 API.

업로드된 문서는 전용 Qdrant 컬렉션(uploaded-docs)에 인덱싱된다.
"""
from fastapi import (APIRouter, BackgroundTasks, Depends, File, HTTPException,
                     UploadFile)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import verify_admin_key
from ..crud import crud_documents
from ..services import document_service
from ..services.document_service import DocumentProcessingError

# 모든 엔드포인트는 X-Admin-API-Key 헤더 인증을 요구한다 (admin_api와 동일)
router = APIRouter(dependencies=[Depends(verify_admin_key)])


def _document_summary(document) -> dict:
    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "status": document.status,
        "chunk_count": document.chunk_count,
        "error": document.error,
        "created_at": document.created_at,
        "started_at": document.started_at,
        "completed_at": document.completed_at,
    }


@router.post("/admin/documents", tags=["Admin - Documents"], status_code=202)
async def upload_document(background_tasks: BackgroundTasks,
                          file: UploadFile = File(...),
                          db: Session = Depends(get_db)):
    """문서(pdf/md/txt)를 업로드해 RAG 인덱싱을 시작합니다.

    인덱싱은 백그라운드에서 진행됩니다 — GET /admin/documents/{id}로
    상태(pending → processing → completed/failed)를 확인하세요.
    """
    try:
        file_type = document_service.get_extension(file.filename or "")
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")
    if len(data) > document_service.MAX_FILE_SIZE:
        limit_mb = document_service.MAX_FILE_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=413, detail=f"파일이 너무 큽니다. 최대 {limit_mb}MB.")

    if crud_documents.get_by_filename(db, file.filename):
        raise HTTPException(
            status_code=409,
            detail="같은 파일명의 문서가 이미 있습니다. 교체하려면 먼저 삭제하세요.")
    try:
        document = crud_documents.create_document(
            db, filename=file.filename, file_type=file_type,
            file_size=len(data))
    except IntegrityError:
        # 사전 조회와 insert 사이의 경쟁 조건 — unique 제약이 최종 방어선
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="같은 파일명의 문서가 이미 있습니다. 교체하려면 먼저 삭제하세요.")

    # UploadFile은 응답 후 닫히므로 bytes를 읽어 태스크에 전달한다
    background_tasks.add_task(
        document_service.process_document,
        document.id, document.filename, document.file_type, data)
    return {
        "message": "문서 인덱싱이 백그라운드에서 시작되었습니다.",
        "document_id": document.id,
        "status": document.status,
    }


@router.get("/admin/documents", tags=["Admin - Documents"])
def list_documents(db: Session = Depends(get_db)):
    """업로드 문서 목록을 최신순으로 반환합니다."""
    return [_document_summary(d) for d in crud_documents.list_documents(db)]


@router.get("/admin/documents/{document_id}", tags=["Admin - Documents"])
def get_document_status(document_id: int, db: Session = Depends(get_db)):
    """문서 하나의 인덱싱 상태를 반환합니다."""
    document = crud_documents.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="해당 문서를 찾을 수 없습니다.")
    return _document_summary(document)


@router.delete("/admin/documents/{document_id}", tags=["Admin - Documents"])
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """문서를 삭제합니다 (Qdrant 포인트 + DB 행). 같은 파일명 재업로드가 가능해집니다."""
    document = crud_documents.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="해당 문서를 찾을 수 없습니다.")
    filename = document.filename  # commit 후에는 인스턴스가 만료되므로 미리 캡처
    try:
        document_service.remove_document(db, document)
    except Exception as exc:
        # Qdrant 삭제 실패 — DB 행을 남겨 재시도할 수 있게 한다
        raise HTTPException(
            status_code=502, detail=f"벡터 삭제에 실패했습니다. 다시 시도하세요. ({exc})")
    return {"message": f"문서 '{filename}'이(가) 삭제되었습니다."}
