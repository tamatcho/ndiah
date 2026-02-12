from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..firebase_auth import get_current_user
from ..db import get_db
from ..models import Document, TimelineItem, User
from ..property_access import get_owned_property_or_404
from ..extractors import extract_timeline
from ..timeline_service import extract_and_store_timeline_for_document

router = APIRouter(prefix="/timeline", tags=["timeline"], dependencies=[Depends(get_current_user)])

class TimelineRequest(BaseModel):
    raw_text: str


class TimelineDocumentsRequest(BaseModel):
    property_id: int
    document_ids: list[int] | None = None


@router.get("")
def list_timeline(
    property_id: int,
    document_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_property_or_404(db, current_user.id, property_id)
    query = db.query(TimelineItem, Document).join(Document, TimelineItem.document_id == Document.id)
    query = query.filter(TimelineItem.property_id == property_id, Document.property_id == property_id)
    if document_id is not None:
        query = query.filter(TimelineItem.document_id == document_id)
    rows = query.order_by(TimelineItem.date_iso.asc(), TimelineItem.time_24h.asc(), TimelineItem.id.asc()).all()

    return [
        {
            "timeline_item_id": item.id,
            "property_id": item.property_id,
            "document_id": item.document_id,
            "filename": doc.filename,
            "document_uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            "title": item.title,
            "date_iso": item.date_iso,
            "time_24h": item.time_24h,
            "category": item.category,
            "amount_eur": item.amount_eur,
            "description": item.description,
        }
        for item, doc in rows
    ]


@router.post("/extract")
def timeline_extract(req: TimelineRequest):
    raw_text = req.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    try:
        result = extract_timeline(raw_text)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Timeline extraction failed")

    return result.model_dump()


@router.post("/extract-documents")
def timeline_extract_documents(
    req: TimelineDocumentsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_property_or_404(db, current_user.id, req.property_id)
    query = db.query(Document).filter(Document.property_id == req.property_id)
    if req.document_ids:
        query = query.filter(Document.id.in_(req.document_ids))
    docs = query.order_by(Document.uploaded_at.asc()).all()
    if not docs:
        raise HTTPException(status_code=400, detail="No documents available for timeline extraction")

    merged_items: list[dict] = []
    failed_documents: list[dict] = []
    processed_documents = 0

    for doc in docs:
        try:
            items = extract_and_store_timeline_for_document(db, doc)
            if not items:
                failed_documents.append({"document_id": doc.id, "filename": doc.filename, "reason": "empty_text"})
                continue
            processed_documents += 1
            merged_items.extend(
                [
                    {
                        **item,
                        "property_id": req.property_id,
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "source": f"Dokument: {doc.filename}",
                    }
                    for item in items
                ]
            )
        except RuntimeError as e:
            failed_documents.append({"document_id": doc.id, "filename": doc.filename, "reason": str(e)})
        except Exception:
            failed_documents.append(
                {"document_id": doc.id, "filename": doc.filename, "reason": "document_timeline_extraction_failed"}
            )

    if not merged_items and failed_documents:
        db.rollback()
        raise HTTPException(status_code=502, detail="Timeline extraction failed for all selected documents")

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Timeline persistence failed")

    merged_items.sort(key=lambda x: (x.get("date_iso") or "", x.get("time_24h") or "99:99", x.get("title") or ""))

    return {
        "items": merged_items,
        "documents_considered": len(docs),
        "documents_processed": processed_documents,
        "documents_failed": failed_documents,
    }


@router.post("/rebuild")
def timeline_rebuild(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_property_or_404(db, current_user.id, property_id)
    docs = db.query(Document).filter(Document.property_id == property_id).order_by(Document.uploaded_at.asc()).all()
    if not docs:
        raise HTTPException(status_code=400, detail="No documents available for timeline rebuild")

    items_count = 0
    for doc in docs:
        try:
            items = extract_and_store_timeline_for_document(db, doc)
            items_count += len(items)
        except RuntimeError as e:
            db.rollback()
            raise HTTPException(status_code=502, detail=str(e))
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="Timeline rebuild failed")

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Timeline persistence failed")

    return {
        "items_count": items_count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
