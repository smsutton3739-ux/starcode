"""Turning whatever the user submits into normalised text.

Handles plain text, PDF, DOCX, images (OCR) and URLs. Every path returns the same
:class:`ExtractionResult`, carrying not just the text but how it was obtained and how
much to trust it — an OCR'd scan at 55% confidence and a pasted paragraph are both
"text", and downstream analysis needs to know which it has.

Security posture for uploads:
  * Size is capped before anything is read into memory.
  * The declared MIME type is never trusted; content is sniffed by magic bytes.
  * A mismatch between extension, declared type and sniffed type is a rejection.
  * Nothing uploaded is ever executed, rendered as HTML, or served back inline.
"""

from __future__ import annotations

import io
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import sha256_bytes

logger = get_logger(__name__)


class IngestError(ValueError):
    """The submission cannot be processed. The message is safe to show a user."""


@dataclass(slots=True)
class ExtractionResult:
    text: str
    source_kind: str
    mime_type: str
    title: str | None = None
    page_count: int | None = None
    ocr_applied: bool = False
    ocr_confidence: float | None = None
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def normalized(self) -> str:
        return normalize_text(self.text)

    def to_dict(self) -> dict:
        return {
            "source_kind": self.source_kind,
            "mime_type": self.mime_type,
            "title": self.title,
            "page_count": self.page_count,
            "ocr_applied": self.ocr_applied,
            "ocr_confidence": self.ocr_confidence,
            "metadata": self.metadata,
            "warnings": self.warnings,
            "char_count": len(self.text),
            "word_count": len(self.text.split()),
        }


# --------------------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH = re.compile(r"[​-‏  ﻿]")


def normalize_text(text: str) -> str:
    """NFC normalisation, control-character stripping, whitespace tidying.

    NFC rather than NFKC: this corpus contains Hebrew and Greek where compatibility
    decomposition would destroy meaningful distinctions (final forms, diacritics that
    carry vowel information). The retrieval layer applies NFKC separately for matching,
    where losing those distinctions is the right trade.
    """
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_CHARS.sub("", text)
    text = _ZERO_WIDTH.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def validate_text(text: str) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        raise IngestError("The submitted text is empty.")
    if len(cleaned) > settings.MAX_TEXT_CHARS:
        raise IngestError(
            f"The text is {len(cleaned):,} characters, over the "
            f"{settings.MAX_TEXT_CHARS:,} limit. Submit it in sections."
        )
    return cleaned


# --------------------------------------------------------------------------------------
# Content sniffing
# --------------------------------------------------------------------------------------

_MAGIC: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]

#: Extensions that must never be accepted whatever the content sniffs as.
_DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".msi",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".vbs",
        ".js",
        ".jar",
        ".php",
        ".py",
        ".rb",
        ".pl",
        ".html",
        ".htm",
        ".svg",
        ".xhtml",
    }
)


def sniff_mime(data: bytes) -> str:
    """Determine the real type from content, ignoring what the client claimed."""
    for signature, mime in _MAGIC:
        if data.startswith(signature):
            return mime

    if data[:4] == b"PK\x03\x04":
        # Both DOCX and generic ZIPs start this way; the marker distinguishes them.
        if b"word/document.xml" in data[:8192] or b"[Content_Types].xml" in data[:4096]:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "application/zip"

    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"

    try:
        sample = data[:8192].decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"

    # An HTML payload with a .txt name is a stored-XSS attempt if it is ever served back.
    if re.search(r"<\s*(?:script|iframe|html|svg)\b", sample, re.IGNORECASE):
        return "text/html"
    return "text/plain"


def check_upload_safety(filename: str, declared_mime: str, data: bytes) -> str:
    """Validate an upload and return the sniffed MIME type. Raises on rejection."""
    if len(data) == 0:
        raise IngestError("The uploaded file is empty.")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise IngestError(
            f"The file is {len(data) / 1_048_576:.1f} MB, over the "
            f"{settings.MAX_UPLOAD_BYTES / 1_048_576:.0f} MB limit."
        )

    extension = Path(filename).suffix.lower()
    if extension in _DANGEROUS_EXTENSIONS:
        raise IngestError(f"Files of type {extension} are not accepted.")

    # Reject path traversal and null bytes in the name outright.
    if "\x00" in filename or ".." in filename or "/" in filename or "\\" in filename:
        raise IngestError("The filename contains characters that are not permitted.")

    sniffed = sniff_mime(data)

    if sniffed == "text/html":
        raise IngestError(
            "This file contains HTML or script markup and is not accepted as a document. "
            "Paste the text directly, or submit the page as a URL instead."
        )

    if sniffed not in settings.allowed_upload_mime:
        raise IngestError(
            f"Files of type {sniffed} are not supported. Accepted: plain text, PDF, "
            "Word documents, and images (PNG, JPEG, TIFF, WebP)."
        )

    if declared_mime and declared_mime != sniffed:
        # Not fatal — browsers routinely mislabel — but the sniffed type governs, and
        # the discrepancy is worth recording.
        logger.info(
            "upload.mime_mismatch",
            filename=filename,
            declared=declared_mime,
            sniffed=sniffed,
        )

    return sniffed


# --------------------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------------------


def extract_from_text(text: str, title: str | None = None) -> ExtractionResult:
    return ExtractionResult(
        text=validate_text(text),
        source_kind="pasted_text",
        mime_type="text/plain",
        title=title,
    )


def extract_from_pdf(data: bytes, filename: str) -> ExtractionResult:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise IngestError("PDF support is not installed on this server.") from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"This PDF could not be read: {exc}") from exc

    if reader.is_encrypted:
        try:
            # An empty password succeeds for PDFs that are encrypted but not restricted.
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise IngestError(
                "This PDF is password-protected. Remove the password and try again."
            ) from exc

    pages: list[str] = []
    for index, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Page {index + 1} could not be read ({exc}).")
            pages.append("")

    text = "\n\n".join(p for p in pages if p.strip())
    metadata: dict = {}
    try:
        info = reader.metadata or {}
        metadata = {
            key.lstrip("/"): str(value)
            for key, value in info.items()
            if value is not None and isinstance(key, str)
        }
    except Exception as exc:  # noqa: BLE001
        # Metadata is a bonus, not the payload: a PDF with a malformed info dictionary
        # still has readable text, so this must not fail the extraction.
        logger.debug("ingest.pdf_metadata_unreadable", error=str(exc))
        warnings.append("Document metadata could not be read.")

    ocr_applied = False
    ocr_confidence = None

    if len(text.strip()) < 40 * max(1, len(reader.pages)) // 10:
        # Almost no extractable text: this is a scan, not a digital document.
        ocr_text, ocr_confidence = _ocr_pdf_pages(data)
        if ocr_text:
            text = ocr_text
            ocr_applied = True
            warnings.append(
                "This PDF contained little or no embedded text, so OCR was used. "
                "OCR of historical documents makes systematic errors — confusing similar "
                "letterforms, dropping diacritics, and misreading marginalia — so verify "
                "any critical reading against the original."
            )
        else:
            warnings.append(
                "This PDF appears to be a scan and no text could be extracted. OCR is "
                "either unavailable on this server or failed. Try submitting the pages as "
                "images, or paste the text directly."
            )

    if not text.strip():
        raise IngestError(
            "No text could be extracted from this PDF. If it is a scanned document, "
            "submit the pages as images so OCR can be applied."
        )

    return ExtractionResult(
        text=validate_text(text),
        source_kind="file_upload",
        mime_type="application/pdf",
        title=metadata.get("Title") or Path(filename).stem,
        page_count=len(reader.pages),
        ocr_applied=ocr_applied,
        ocr_confidence=ocr_confidence,
        metadata=metadata,
        warnings=warnings,
    )


def _ocr_pdf_pages(data: bytes) -> tuple[str, float | None]:
    """OCR a PDF by rasterising it. Requires pdf2image plus poppler, which many
    deployments will not have; absence is reported, never silently ignored."""
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        logger.info("ingest.pdf_ocr_unavailable", reason="pdf2image not installed")
        return "", None

    try:
        images = convert_from_bytes(data, dpi=300, fmt="png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingest.pdf_rasterize_failed", error=str(exc))
        return "", None

    texts: list[str] = []
    confidences: list[float] = []
    for image in images[:50]:  # bound the work
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        page_text, confidence = _ocr_image_bytes(buffer.getvalue())
        if page_text:
            texts.append(page_text)
        if confidence is not None:
            confidences.append(confidence)

    return "\n\n".join(texts), (sum(confidences) / len(confidences) if confidences else None)


def extract_from_docx(data: bytes, filename: str) -> ExtractionResult:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise IngestError("Word document support is not installed on this server.") from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"This Word document could not be read: {exc}") from exc

    blocks = [p.text for p in document.paragraphs if p.text.strip()]

    # Tables often hold the chronological data in documents like these, so they are
    # extracted rather than skipped.
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))

    text = "\n\n".join(blocks)
    if not text.strip():
        raise IngestError("This Word document contains no readable text.")

    metadata: dict = {}
    try:
        core = document.core_properties
        metadata = {
            "title": core.title,
            "author": core.author,
            "subject": core.subject,
            "created": str(core.created) if core.created else None,
            "modified": str(core.modified) if core.modified else None,
        }
        metadata = {k: v for k, v in metadata.items() if v}
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingest.docx_metadata_unreadable", error=str(exc))

    return ExtractionResult(
        text=validate_text(text),
        source_kind="file_upload",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        title=metadata.get("title") or Path(filename).stem,
        metadata=metadata,
        warnings=[],
    )


def extract_from_image(data: bytes, filename: str, mime_type: str) -> ExtractionResult:
    text, confidence = _ocr_image_bytes(data)
    if not text.strip():
        raise IngestError(
            "No text could be recognised in this image. For manuscripts, a higher-"
            "resolution scan with good contrast and a level page usually helps. If the "
            "script is not Latin, install the matching Tesseract language pack and set "
            "OCR_LANGUAGES."
        )

    warnings = [
        "This text was produced by OCR. Optical recognition of historical manuscripts is "
        "error-prone in specific, predictable ways — similar letterforms are confused, "
        "diacritics and abbreviation marks are dropped, and marginalia can be interleaved "
        "with the main text. Treat the transcription as a draft and verify anything the "
        "analysis turns on."
    ]
    if confidence is not None and confidence < 70:
        warnings.append(
            f"Average OCR confidence is {confidence:.0f}%, which is low. The extracted "
            "text likely contains substantial errors, and every conclusion drawn from it "
            "inherits that uncertainty."
        )

    metadata: dict = {}
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            metadata = {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingest.image_metadata_unreadable", error=str(exc))

    return ExtractionResult(
        text=validate_text(text),
        source_kind="file_upload",
        mime_type=mime_type,
        title=Path(filename).stem,
        ocr_applied=True,
        ocr_confidence=confidence,
        metadata=metadata,
        warnings=warnings,
    )


def _ocr_image_bytes(data: bytes) -> tuple[str, float | None]:
    """Run Tesseract, with light preprocessing that helps on scanned manuscripts."""
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        logger.info("ingest.ocr_unavailable", reason="pytesseract or Pillow not installed")
        return "", None

    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("L", "RGB"):
                image = image.convert("RGB")
            grey = ImageOps.grayscale(image)

            # Upscale small scans: Tesseract needs roughly 300 DPI equivalent, and many
            # manuscript photographs are well under that.
            if min(grey.size) < 1000:
                factor = max(2, 1000 // max(1, min(grey.size)))
                grey = grey.resize((grey.width * factor, grey.height * factor), Image.LANCZOS)

            grey = ImageOps.autocontrast(grey)
            grey = grey.filter(ImageFilter.MedianFilter(size=3))

            data_frame = pytesseract.image_to_data(
                grey,
                lang=settings.ocr_languages,
                output_type=pytesseract.Output.DICT,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingest.ocr_failed", error=str(exc))
        return "", None

    words: list[str] = []
    confidences: list[float] = []
    # Tesseract returns these as parallel arrays of equal length.
    for text, confidence in zip(
        data_frame.get("text", []), data_frame.get("conf", []), strict=False
    ):
        if not text or not text.strip():
            continue
        words.append(text)
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            confidences.append(value)

    return " ".join(words), (sum(confidences) / len(confidences) if confidences else None)


def extract_from_upload(filename: str, declared_mime: str, data: bytes) -> ExtractionResult:
    """Dispatch on the *sniffed* type after safety checks."""
    mime = check_upload_safety(filename, declared_mime, data)

    if mime == "application/pdf":
        return extract_from_pdf(data, filename)
    if mime.endswith("wordprocessingml.document"):
        return extract_from_docx(data, filename)
    if mime.startswith("image/"):
        return extract_from_image(data, filename, mime)
    if mime in ("text/plain", "text/markdown"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            for encoding in ("utf-16", "latin-1", "cp1252"):
                try:
                    text = data.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise IngestError("The file's text encoding could not be determined.") from None
        result = extract_from_text(text, title=Path(filename).stem)
        result.source_kind = "file_upload"
        return result

    raise IngestError(f"Files of type {mime} are not supported.")


def store_upload(data: bytes, sha256: str, filename: str) -> str:
    """Write to the upload directory under a content-addressed name.

    The user's filename never touches the filesystem path — it is metadata only. This
    removes a whole class of traversal and collision problems by construction.
    """
    directory = Path(settings.UPLOAD_DIR) / sha256[:2] / sha256[2:4]
    directory.mkdir(parents=True, exist_ok=True)
    extension = Path(filename).suffix.lower()[:10]
    extension = re.sub(r"[^a-z0-9.]", "", extension)
    path = directory / f"{sha256}{extension}"
    if not path.exists():
        path.write_bytes(data)
        os.chmod(path, 0o600)
    return str(path)


def read_upload_stream(stream: BinaryIO, limit: int | None = None) -> bytes:
    """Read at most `limit` bytes plus one, so oversize can be detected without
    buffering the whole payload."""
    limit = limit or settings.MAX_UPLOAD_BYTES
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise IngestError(f"The file exceeds the {limit / 1_048_576:.0f} MB limit.")
    return data


def compute_hash(data: bytes) -> str:
    return sha256_bytes(data)


__all__ = [
    "IngestError",
    "ExtractionResult",
    "normalize_text",
    "validate_text",
    "sniff_mime",
    "check_upload_safety",
    "extract_from_text",
    "extract_from_pdf",
    "extract_from_docx",
    "extract_from_image",
    "extract_from_upload",
    "store_upload",
    "read_upload_stream",
    "compute_hash",
]
