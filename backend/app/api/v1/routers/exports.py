"""Export endpoints."""

from __future__ import annotations

import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import (
    DbSession,
    OptionalUser,
    get_anonymous_token,
    get_owned_or_shared_analysis,
    rate_limiter,
    record_audit,
)
from app.db.models.ops import AuditAction
from app.services.export import EXPORT_FORMATS, ExportError, export_analysis

router = APIRouter(prefix="/analyses", tags=["exports"])


@router.get(
    "/{analysis_id}/export/{fmt}",
    dependencies=[Depends(rate_limiter("export"))],
    summary="Export a report as PDF, DOCX, CSV, Markdown or JSON",
    response_class=Response,
)
def export(
    analysis_id: str,
    fmt: str,
    request: Request,
    db: DbSession,
    user: OptionalUser,
    anonymous_token: Annotated[str | None, Depends(get_anonymous_token)] = None,
) -> Response:
    analysis = get_owned_or_shared_analysis(db, analysis_id, user, anonymous_token)

    try:
        content, mime_type, filename = export_analysis(analysis, fmt.lower())
    except ExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_audit(
        db, AuditAction.ANALYSIS_EXPORTED, actor=user, target_type="analysis",
        target_id=analysis_id, request=request, detail={"format": fmt},
    )
    db.commit()

    # RFC 5987 encoding so non-ASCII titles survive the header intact.
    quoted = urllib.parse.quote(filename)
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}",
            "Content-Length": str(len(content)),
            # Reports can contain personal research; never let a shared cache keep one.
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{analysis_id}/export", summary="List available export formats")
def formats(
    analysis_id: str,
    db: DbSession,
    user: OptionalUser,
    anonymous_token: Annotated[str | None, Depends(get_anonymous_token)] = None,
) -> dict:
    analysis = get_owned_or_shared_analysis(db, analysis_id, user, anonymous_token)
    ready = bool(analysis.reports)
    return {
        "analysis_id": analysis_id,
        "ready": ready,
        "formats": [
            {
                "format": fmt,
                "url": f"/api/v1/analyses/{analysis_id}/export/{fmt}",
                "description": {
                    "pdf": "Formatted report with colour-coded claim types.",
                    "docx": "Editable Word document with the same structure.",
                    "csv": "One row per claim, with the claim type as a column.",
                    "markdown": "Plain-text report for notes and version control.",
                    "json": "Complete structured data, including the claim-type vocabulary.",
                }[fmt],
            }
            for fmt in EXPORT_FORMATS
        ],
        "note": (
            "Every format preserves the claim-type labelling. Nothing exported drops the "
            "distinction between a calculation and a conjecture."
        )
        if ready
        else "The analysis has not finished; exports become available when it completes.",
    }


__all__ = ["router"]
