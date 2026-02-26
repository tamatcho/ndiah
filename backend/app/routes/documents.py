import os
import re
import io
import zipfile
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from sqlalchemy.orm import Session

from ..firebase_auth import get_current_user
from ..config import settings
from ..db import get_db, SessionLocal
from ..models import Chunk, Document, Property, TimelineItem, User
from ..pdf_ingest import extract_text_from_pdf_bytes, simple_chunk
from ..property_access import get_owned_property_or_404
from ..rag import upsert_chunks
from ..timeline_service import extract_and_store_timeline_for_document

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)])
MAX_ZIP_PDF_FILES = 100
MAX_ZIP_TOTAL_PDF_BYTES = 200 * 1024 * 1024


PDF_CONTENT_TYPES = {"application/pdf"}
ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed"}


def _sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename or "").strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe


def _is_pdf_upload(filename: str, content_type: str | None) -> bool:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    return name.endswith(".pdf") or ctype in PDF_CONTENT_TYPES


def _is_zip_upload(filename: str, content_type: str | None) -> bool:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    return name.endswith(".zip") or ctype in ZIP_CONTENT_TYPES


def _ensure_property_document_limit_not_exceeded(db: Session, property_id: int, incoming_docs: int = 1) -> None:
    docs_count_for_property = db.query(Document).filter(Document.property_id == property_id).count()
    if docs_count_for_property + incoming_docs > settings.FREE_TIER_MAX_DOCUMENTS_PER_PROPERTY:
        raise HTTPException(
            status_code=429,
            detail=(
                "Limit erreicht: Maximal "
                f"{settings.FREE_TIER_MAX_DOCUMENTS_PER_PROPERTY} Dokumente pro Immobilie im Free-Tarif."
            ),
        )


def _ingest_pdf_content(db: Session, property_obj: Property, filename: str, content: bytes) -> dict:
    _ensure_property_document_limit_not_exceeded(db, property_obj.id, incoming_docs=1)

    safe_filename = _sanitize_filename(filename)
    if not safe_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien sind erlaubt.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Die hochgeladene Datei ist kein gültiges PDF.")
    if len(content) > settings.MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu groß: Maximal {settings.MAX_PDF_BYTES // (1024 * 1024)} MB pro PDF.",
        )

    doc = Document(
        property_id=property_obj.id,
        filename=safe_filename,
        path=None,
        file_bytes=content,
        content_type="application/pdf",
    )
    try:
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Dokumentmetadaten konnten nicht gespeichert werden.")

    try:
        text = extract_text_from_pdf_bytes(content)
    except Exception:
        raise HTTPException(status_code=400, detail="PDF konnte nicht gelesen werden.")
    doc.extracted_text = text

    chunks = simple_chunk(text, with_metadata=True)
    payload = [
        {
            "document_id": doc.id,
            "chunk_id": f"{doc.id}-p{int(ch['page'])}-{int(ch['page_chunk_index'])}",
            "text": str(ch["text"]),
        }
        for ch in chunks
    ]

    try:
        upsert_chunks(db, payload)
    except RuntimeError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Indexierung der Dokumentinhalte fehlgeschlagen.")

    try:
        timeline_items = extract_and_store_timeline_for_document(db, doc, raw_text=text)
        db.commit()
    except RuntimeError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Timeline-Extraktion fehlgeschlagen.")

    return {
        "document_id": doc.id,
        "property_id": doc.property_id,
        "filename": doc.filename,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "chunks_indexed": len(payload),
        "timeline_items_upserted": len(timeline_items),
    }


def _process_zip_in_background(property_id: int, zip_content: bytes) -> None:
    db = SessionLocal()
    try:
        property_obj = db.query(Property).filter(Property.id == property_id).first()
        if not property_obj:
            return
        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            pdf_entries = [entry for entry in entries if entry.filename.lower().endswith(".pdf")]
            for entry in pdf_entries:
                try:
                    inner_name = _sanitize_filename(entry.filename)
                    inner_content = archive.read(entry)
                    if len(inner_content) > settings.MAX_PDF_BYTES:
                        continue
                    if not inner_content.startswith(b"%PDF"):
                        continue
                    _ingest_pdf_content(db, property_obj, inner_name, inner_content)
                except Exception:
                    db.rollback()
                    continue
    finally:
        db.close()


@router.get("/status")
def documents_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    docs_count = (
        db.query(Document)
        .join(Property, Document.property_id == Property.id)
        .filter(Property.user_id == current_user.id)
        .count()
    )
    chunk_count = (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .join(Property, Document.property_id == Property.id)
        .filter(Property.user_id == current_user.id)
        .count()
    )
    return {
        "documents_in_db": docs_count,
        "chunks_in_db": chunk_count,
    }


@router.get("")
def list_documents(
    property_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if property_id is not None:
        get_owned_property_or_404(db, current_user.id, property_id)

    query = (
        db.query(Document)
        .join(Property, Document.property_id == Property.id)
        .filter(Property.user_id == current_user.id)
    )
    if property_id is not None:
        query = query.filter(Document.property_id == property_id)
    docs = query.order_by(Document.uploaded_at.desc()).all()
    return [
        {
            "document_id": d.id,
            "property_id": d.property_id,
            "filename": d.filename,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


@router.get("/source")
def get_source_snippet(
    document_id: int,
    chunk_id: str,
    max_chars: int = 1200,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = (
        db.query(Document)
        .join(Property, Document.property_id == Property.id)
        .filter(Document.id == document_id, Property.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk = db.query(Chunk).filter(Chunk.document_id == document_id, Chunk.chunk_id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Source chunk not found")

    safe_max_chars = max(1, min(max_chars, 5000))
    text = chunk.text or ""
    return {
        "document_id": document_id,
        "property_id": doc.property_id,
        "chunk_id": chunk_id,
        "filename": doc.filename,
        "snippet": text[:safe_max_chars],
        "total_chars": len(text),
    }


@router.post("/upload")
async def upload_pdf(
    property_id: int = Form(...),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_obj = get_owned_property_or_404(db, current_user.id, property_id)
    safe_filename = _sanitize_filename(file.filename)
    content = await file.read()
    content_type = getattr(file, "content_type", None)

    if not (_is_pdf_upload(safe_filename, content_type) or _is_zip_upload(safe_filename, content_type)):
        raise HTTPException(status_code=400, detail="Nur PDF- oder ZIP-Dateien sind erlaubt.")

    if _is_pdf_upload(safe_filename, content_type) and not safe_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Bitte lade eine PDF-Datei mit der Endung .pdf hoch.")

    if _is_zip_upload(safe_filename, content_type) and not safe_filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Bitte lade eine ZIP-Datei mit der Endung .zip hoch.")

    if safe_filename.lower().endswith(".pdf") and len(content) > settings.MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu groß: Maximal {settings.MAX_PDF_BYTES // (1024 * 1024)} MB pro PDF.",
        )

    if safe_filename.lower().endswith(".pdf"):
        _ensure_property_document_limit_not_exceeded(db, property_obj.id, incoming_docs=1)
        return _ingest_pdf_content(db, property_obj, safe_filename, content)

    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(status_code=400, detail="Die hochgeladene ZIP-Datei ist ungültig.")

    with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        pdf_entries = [entry for entry in entries if entry.filename.lower().endswith(".pdf")]
        if not pdf_entries:
            raise HTTPException(status_code=400, detail="Die ZIP-Datei enthält keine PDF-Dateien.")
        if len(pdf_entries) > MAX_ZIP_PDF_FILES:
            raise HTTPException(status_code=400, detail=f"Zu viele PDFs in der ZIP-Datei (max. {MAX_ZIP_PDF_FILES}).")
        _ensure_property_document_limit_not_exceeded(db, property_obj.id, incoming_docs=len(pdf_entries))
        total_pdf_size = sum(entry.file_size for entry in pdf_entries)
        if total_pdf_size > MAX_ZIP_TOTAL_PDF_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Gesamtgröße der PDFs in der ZIP überschreitet das Limit ({MAX_ZIP_TOTAL_PDF_BYTES} Bytes).",
            )
    if background_tasks is not None:
        background_tasks.add_task(_process_zip_in_background, property_obj.id, content)
    else:
        _process_zip_in_background(property_obj.id, content)

    return {
        "archive_filename": safe_filename,
        "property_id": property_obj.id,
        "processed_count": 0,
        "failed_count": 0,
        "timeline_items_upserted": 0,
        "documents": [],
        "failed_documents": [],
        "queued": True,
        "message": "ZIP-Verarbeitung wurde gestartet. Dokumente erscheinen nach der Hintergrundverarbeitung.",
    }


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    property_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_property_or_404(db, current_user.id, property_id)
    doc = db.query(Document).filter(Document.id == document_id, Document.property_id == property_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    try:
        deleted_chunks = (
            db.query(Chunk)
            .filter(Chunk.document_id == doc.id)
            .delete(synchronize_session=False)
        )
        deleted_timeline_items = (
            db.query(TimelineItem)
            .filter(TimelineItem.document_id == doc.id)
            .delete(synchronize_session=False)
        )
        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Dokument konnte nicht gelöscht werden")

    return {
        "ok": True,
        "document_id": document_id,
        "property_id": property_id,
        "deleted_chunks": deleted_chunks,
        "deleted_timeline_items": deleted_timeline_items,
    }
