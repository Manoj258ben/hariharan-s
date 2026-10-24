"""
Database Administration, Storage Metrics, Backup, and Controlled Restore Router.
Strictly restricted to administrators.
"""
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.auth import User
from ..config import BACKUP_DIR
from ..services.auth import require_admin
from ..services.backup import (
    get_database_stats,
    create_database_backup,
    list_backups,
    restore_database_backup,
)

router = APIRouter(prefix="/api/admin/backup", tags=["Database Backup & Administration"])


class BackupCreateRequest(BaseModel):
    note: Optional[str] = "Manual administrative backup"


class RestoreRequest(BaseModel):
    backup_filename: str = Field(min_length=1)
    confirm_text: str = Field(description="Must match 'CONFIRM_RESTORE' to execute")


@router.get("/health")
def get_db_health(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Returns database size, WAL status, table row counts, and SQLite integrity check."""
    return get_database_stats(db)


@router.post("/create")
def trigger_backup(
    req: BackupCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Creates a consistent, validated SQLite backup file."""
    try:
        backup_info = create_database_backup(
            db=db,
            actor_id=admin.id,
            actor_username=admin.username,
            note=req.note or "Manual backup",
        )
        return {"status": "success", "backup": backup_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup creation failed: {str(e)}")


@router.get("/list")
def get_backup_list(admin: User = Depends(require_admin)):
    """List all available SQLite backups on the server."""
    return list_backups()


@router.get("/download/{filename}")
def download_backup_file(
    filename: str,
    admin: User = Depends(require_admin)
):
    """Download a verified SQLite backup database file."""
    safe_filename = Path(filename).name
    file_path = BACKUP_DIR / safe_filename

    if not file_path.exists() or not safe_filename.endswith(".db"):
        raise HTTPException(status_code=404, detail="Requested backup file not found.")

    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type="application/x-sqlite3",
    )


@router.post("/restore")
def restore_backup(
    req: RestoreRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Restores the live database from a selected backup.
    Requires explicit confirmation 'CONFIRM_RESTORE'.
    Creates a pre-restore safety snapshot before applying the restore.
    """
    if req.confirm_text != "CONFIRM_RESTORE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Safety confirmation failed. You must provide confirm_text='CONFIRM_RESTORE'.",
        )

    try:
        result = restore_database_backup(
            backup_filename=req.backup_filename,
            db=db,
            actor_id=admin.id,
            actor_username=admin.username,
        )
        return result
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database restore failed: {str(e)}")
