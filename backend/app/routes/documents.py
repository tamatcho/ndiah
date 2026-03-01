import logging
import os
import re
import io
import json
import zipfile
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from ..firebase_auth import get_current_user
from ..config import settings
from ..db import get_db, SessionLocal
from ..models import Chunk, Document, Property, TimelineItem, UploadJob, User
from ..pdf_ingest import extract_text_and_quality_from_pdf_bytes, extract_text_from_pdf_bytes, simple_chunk
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
        db.flush()  # get doc.id from DB sequence without committing

        logger.info("Ingesting PDF property_id=%d filename=%s size_bytes=%d", property_obj.id, safe_filename, len(content))

        text, quality_score = extract_text_and_quality_from_pdf_bytes(content)
        doc.extracted_text = text
        doc.quality_score = quality_score

        if quality_score < settings.PDF_QUALITY_WARN_THRESHOLD:
            logger.warning("Low quality PDF property_id=%d filename=%s quality_score=%.3f", property_obj.id, safe_filename, quality_score)

        chunks = simple_chunk(text, with_metadata=True)
        payload = [
            {
                "document_id": doc.id,
                "chunk_id": f"{doc.id}-p{int(ch['page'])}-{int(ch['page_chunk_index'])}",
                "text": str(ch["text"]),
            }
            for ch in chunks
        ]
        upsert_chunks(db, payload)

        timeline_items = extract_and_store_timeline_for_document(db, doc, raw_text=text)

        db.commit()  # single commit: doc + chunks + timeline together
        logger.info("Ingested PDF property_id=%d filename=%s chunks=%d timeline_items=%d quality=%.3f", property_obj.id, safe_filename, len(payload), len(timeline_items), quality_score)
    except HTTPException:
        db.rollback()
        raise
    except RuntimeError as e:
        db.rollback()
        logger.error("PDF ingest failed (OpenAI) property_id=%d filename=%s error=%s", property_obj.id, safe_filename, str(e))
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        db.rollback()
        logger.exception("PDF ingest failed property_id=%d filename=%s", property_obj.id, safe_filename)
        raise HTTPException(status_code=500, detail="Dokumentverarbeitung fehlgeschlagen.")

    result: dict = {
        "document_id": doc.id,
        "property_id": doc.property_id,
        "filename": doc.filename,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "chunks_indexed": len(payload),
        "timeline_items_upserted": len(timeline_items),
        "quality_score": quality_score,
    }
    if quality_score < settings.PDF_QUALITY_WARN_THRESHOLD:
        result["low_quality"] = True
        result["quality_warning"] = (
            f"PDF-Qualität niedrig (Score: {quality_score:.2f}). "
            "Das Dokument enthält möglicherweise hauptsächlich Bilder ohne erkannten Text. "
            "Antworten und Timeline könnten unvollständig sein."
        )
    return result


def _process_zip_in_background(job_id: int, property_id: int, zip_content: bytes) -> None:
    db = SessionLocal()
    try:
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        property_obj = db.query(Property).filter(Property.id == property_id).first()
        if not property_obj:
            job.status = "failed"
            db.commit()
            return

        processed_count = 0
        failed_count = 0
        failed_filenames: list[str] = []

        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            pdf_entries = [entry for entry in entries if entry.filename.lower().endswith(".pdf")]
            logger.info("ZIP processing job_id=%d property_id=%d total_pdfs=%d", job_id, property_id, len(pdf_entries))
            for entry in pdf_entries:
                try:
                    inner_name = _sanitize_filename(entry.filename)
                    inner_content = archive.read(entry)
                    if len(inner_content) > settings.MAX_PDF_BYTES or not inner_content.startswith(b"%PDF"):
                        failed_count += 1
                        failed_filenames.append(inner_name)
                        logger.warning("ZIP PDF skipped job_id=%d filename=%s reason=invalid_or_too_large", job_id, inner_name)
                        continue
                    _ingest_pdf_content(db, property_obj, inner_name, inner_content)
                    processed_count += 1
                except Exception as exc:
                    db.rollback()
                    failed_count += 1
                    failed_filenames.append(entry.filename)
                    logger.warning("ZIP PDF failed job_id=%d filename=%s error=%s", job_id, entry.filename, str(exc))

        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if job:
            job.status = "completed"
            job.processed_count = processed_count
            job.failed_count = failed_count
            job.failed_filenames = json.dumps(failed_filenames, ensure_ascii=False)
            db.commit()
        logger.info("ZIP completed job_id=%d processed=%d failed=%d", job_id, processed_count, failed_count)
    except Exception:
        db.rollback()
        logger.exception("ZIP background task crashed job_id=%d property_id=%d", job_id, property_id)
        try:
            job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
            if job:
                job.status = "failed"
                db.commit()
        except Exception:
            pass
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
            "quality_score": d.quality_score,
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
    job = UploadJob(property_id=property_obj.id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    if background_tasks is not None:
        background_tasks.add_task(_process_zip_in_background, job.id, property_obj.id, content)
    else:
        _process_zip_in_background(job.id, property_obj.id, content)

    return {
        "archive_filename": safe_filename,
        "property_id": property_obj.id,
        "job_id": job.id,
        "queued": True,
        "message": "ZIP-Verarbeitung wurde gestartet. Dokumente erscheinen nach der Hintergrundverarbeitung.",
    }


@router.get("/upload-jobs/{job_id}")
def get_upload_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = (
        db.query(UploadJob)
        .join(Property, UploadJob.property_id == Property.id)
        .filter(UploadJob.id == job_id, Property.user_id == current_user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Upload-Job nicht gefunden")
    failed_filenames: list[str] = []
    if job.failed_filenames:
        try:
            failed_filenames = json.loads(job.failed_filenames)
        except Exception:
            pass
    return {
        "job_id": job.id,
        "property_id": job.property_id,
        "status": job.status,
        "processed_count": job.processed_count,
        "failed_count": job.failed_count,
        "failed_filenames": failed_filenames,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
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
