"""Documents Storage & Certificate Upload Router for Q-Transplant v2."""
import uuid
import os
from pathlib import Path
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Document
from app.security import get_current_user
from app.config import settings, BASE_DIR

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg", "doc", "docx"}
MAX_BYTES = 15 * 1024 * 1024 # 15 MB
DOCS_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(DOCS_DIR, exist_ok=True)

@router.post("/public-upload")
def public_upload_document(file: UploadFile = File(...), kind: str = "registration_doc"):
    """Public upload endpoint for Doctor Aadhaar & Govt Accreditation files during registration."""
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"File extension '.{ext}' is not allowed. Supported formats: {', '.join(ALLOWED_EXT)}")

    file_id = str(uuid.uuid4())
    stored_name = f"{file_id}.{ext}"
    storage_path = os.path.join(DOCS_DIR, stored_name)

    contents = file.file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds maximum 15MB limit.")

    with open(storage_path, "wb") as f:
        f.write(contents)

    file_url = f"/uploads/{stored_name}"
    return {
        "filename": file.filename,
        "kind": kind,
        "url": file_url,
        "stored_name": stored_name
    }

@router.post("/upload")
def upload_document(file: UploadFile = File(...), kind: str = "certificate", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Uploads a document (government certificate, accreditation proof, or medical document)."""
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"File extension '.{ext}' is not allowed. Supported: {', '.join(ALLOWED_EXT)}")

    file_id = str(uuid.uuid4())
    stored_name = f"{file_id}.{ext}"
    storage_path = os.path.join(DOCS_DIR, stored_name)

    contents = file.file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds maximum 15MB limit.")

    with open(storage_path, "wb") as f:
        f.write(contents)

    doc = Document(
        id=file_id,
        owner_user_id=user.id,
        kind=kind,
        filename=file.filename,
        storage_path=storage_path,
        verification_status="verified"
    )
    db.add(doc)
    db.commit()

    file_url = f"/api/v1/documents/{file_id}/download"
    return {
        "id": doc.id,
        "filename": doc.filename,
        "kind": doc.kind,
        "url": file_url
    }

@router.get("/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db)):
    """Downloads/views an uploaded document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(doc.storage_path, filename=doc.filename)
