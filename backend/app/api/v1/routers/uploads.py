"""File uploads and URL ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, OptionalUser, rate_limiter, record_audit
from app.core.logging import get_logger
from app.db.models.content import Upload, UploadStatus
from app.db.models.ops import AuditAction
from app.schemas.analysis import UploadOut, UploadResult, UrlPreview
from app.services import analysis_service
from app.services.ingest import (
    IngestError,
    compute_hash,
    extract_from_upload,
    read_upload_stream,
    store_upload,
)
from app.services.url_fetch import FetchError, fetch_as_extraction

logger = get_logger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadResult, dependencies=[Depends(rate_limiter("upload"))])
def upload_file(
    request: Request,
    db: DbSession,
    user: OptionalUser,
    file: UploadFile = File(..., description="PDF, DOCX, image or plain text"),
) -> UploadResult:
    """Accept a file, extract its text, and return a document ready to analyse."""
    filename = file.filename or "upload"

    try:
        data = read_upload_stream(file.file)
    except IngestError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    sha256 = compute_hash(data)

    # Same file from the same owner: reuse rather than re-OCR. OCR is the expensive step
    # and re-running it would produce the same result at real cost.
    existing = (
        db.execute(
            select(Upload).where(
                Upload.sha256 == sha256,
                Upload.owner_id == (user.id if user else None),
                Upload.status == UploadStatus.READY,
            )
        )
        .scalars()
        .first()
    )

    if existing is not None:
        document = existing.documents[0] if existing.documents else None
        if document is not None:
            return UploadResult(
                upload=UploadOut.model_validate(
                    {**existing.__dict__, "status": existing.status.value}
                ),
                document_id=document.id,
                extracted_characters=document.char_count,
                ocr_applied=document.ocr_applied,
                ocr_confidence=document.ocr_confidence,
                warnings=["This file was uploaded before; the existing extraction was reused."],
                preview=document.raw_text[:600],
            )

    upload = Upload(
        owner_id=user.id if user else None,
        original_filename=filename[:500],
        stored_path="",
        mime_type=file.content_type or "application/octet-stream",
        byte_size=len(data),
        sha256=sha256,
        status=UploadStatus.SCANNING,
    )
    db.add(upload)
    db.flush()

    try:
        extraction = extract_from_upload(filename, file.content_type or "", data)
    except IngestError as exc:
        upload.status = UploadStatus.REJECTED
        upload.rejection_reason = str(exc)[:500]
        record_audit(
            db,
            AuditAction.UPLOAD_REJECTED,
            actor=user,
            target_type="upload",
            target_id=upload.id,
            outcome="rejected",
            request=request,
            detail={"filename": filename, "reason": str(exc)[:300]},
        )
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    upload.stored_path = store_upload(data, sha256, filename)
    upload.detected_mime_type = extraction.mime_type
    upload.page_count = extraction.page_count
    upload.file_metadata = extraction.metadata
    upload.status = UploadStatus.READY

    document = analysis_service.create_document(db, extraction, owner=user, upload_id=upload.id)

    record_audit(
        db,
        AuditAction.UPLOAD_RECEIVED,
        actor=user,
        target_type="upload",
        target_id=upload.id,
        request=request,
        detail={
            "filename": filename,
            "mime": extraction.mime_type,
            "bytes": len(data),
            "ocr": extraction.ocr_applied,
        },
    )
    db.commit()

    return UploadResult(
        upload=UploadOut.model_validate({**upload.__dict__, "status": upload.status.value}),
        document_id=document.id,
        extracted_characters=document.char_count,
        ocr_applied=extraction.ocr_applied,
        ocr_confidence=extraction.ocr_confidence,
        warnings=extraction.warnings,
        preview=document.raw_text[:600],
    )


class UrlRequest(BaseModel):
    url: str = Field(max_length=2048)


@router.post("/url", response_model=UrlPreview, dependencies=[Depends(rate_limiter("upload"))])
def ingest_url(
    payload: UrlRequest,
    request: Request,
    db: DbSession,
    user: OptionalUser,
) -> UrlPreview:
    """Fetch a URL and extract its readable text."""
    try:
        extraction = fetch_as_extraction(payload.url)
    except FetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document = analysis_service.create_document(db, extraction, owner=user, source_url=payload.url)
    record_audit(
        db,
        AuditAction.URL_FETCHED,
        actor=user,
        target_type="document",
        target_id=document.id,
        request=request,
        detail={"url": payload.url},
    )
    db.commit()

    return UrlPreview(
        url=payload.url,
        final_url=extraction.metadata.get("final_url", payload.url),
        title=extraction.title,
        document_id=document.id,
        extracted_characters=document.char_count,
        preview=document.raw_text[:600],
        warnings=extraction.warnings,
    )


@router.get("/limits")
def limits() -> dict:
    """What this server accepts — used by the drag-and-drop UI to validate early."""
    from app.core.config import settings

    return {
        "max_upload_bytes": settings.MAX_UPLOAD_BYTES,
        "max_upload_mb": round(settings.MAX_UPLOAD_BYTES / 1_048_576, 1),
        "max_text_characters": settings.MAX_TEXT_CHARS,
        "accepted_mime_types": sorted(settings.allowed_upload_mime),
        "accepted_extensions": [
            ".txt",
            ".md",
            ".pdf",
            ".docx",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".webp",
        ],
        "ocr_languages": settings.OCR_LANGUAGES,
        "notes": [
            "Files are identified by their contents, not their extension.",
            "HTML and script files are refused; submit the page as a URL instead.",
            "Scanned documents are OCR'd automatically, and the result is flagged as OCR "
            "with its confidence so you can judge how much to trust it.",
        ],
    }


__all__ = ["router"]
