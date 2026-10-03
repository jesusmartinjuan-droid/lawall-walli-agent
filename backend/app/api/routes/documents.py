from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService
from app.services.openai_file_service import FileTooLargeError, UnsupportedFileTypeError

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _to_response(document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        original_filename=document.original_filename,
        content_type=document.content_type,
        is_active=document.is_active,
        size_bytes=document.size_bytes,
        openai_file_id=document.openai_file_id,
        openai_file_uploaded_at=document.openai_file_uploaded_at,
        openai_upload_error=document.openai_upload_error,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_to_response(d) for d in DocumentService(db).list_documents()]


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = DocumentService(db)
    file_bytes = await file.read()
    try:
        document = service.upload(
            original_filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            file_bytes=file_bytes,
        )
    except (UnsupportedFileTypeError, FileTooLargeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(document)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    document = DocumentService(db).get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return _to_response(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    deleted = DocumentService(db).delete(document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
