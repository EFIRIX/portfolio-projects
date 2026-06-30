"""User files endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.social import FileDeleteResponse, FileListOut, FileOut
from app.services import file_service
from app.services.s3 import delete_file_from_storage

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=FileListOut, status_code=status.HTTP_200_OK)
async def get_user_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    files = await file_service.get_user_files(db=db, user_id=current_user.id)
    file_items = [
        FileOut(
            id=file.id,
            file_name=file.file_name,
            mime_type=file.mime_type,
            file_size=file.file_size,
            created_at=file.created_at,
            download_url=file_service.get_file_download_url(file.storage_key),
        )
        for file in files
    ]
    return FileListOut(files=file_items, total_count=len(file_items))


@router.delete("/{file_id}", response_model=FileDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_user_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file = await file_service.get_file_by_id(db=db, file_id=file_id, user_id=current_user.id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    storage_deleted = delete_file_from_storage(storage_key=file.storage_key, bucket_name="uploads")
    if not storage_deleted:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to delete file from storage",
        )

    db.delete(file)
    db.commit()

    return FileDeleteResponse(success=True, message="File deleted successfully")
