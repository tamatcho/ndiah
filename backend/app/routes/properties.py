from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..firebase_auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import ChatMessage, Chunk, Document, Property, TimelineItem, UploadJob, User
from ..property_access import get_owned_property_or_404

router = APIRouter(prefix="/properties", tags=["properties"], dependencies=[Depends(get_current_user)])


class CreatePropertyBody(BaseModel):
    name: str
    address_optional: str | None = None


class PatchPropertyBody(BaseModel):
    name: str | None = None
    address_optional: str | None = None


def _serialize_property(row: Property) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "address_optional": row.address_optional,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
def list_properties(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Property)
        .filter(Property.user_id == current_user.id)
        .order_by(Property.created_at.desc(), Property.id.desc())
        .all()
    )
    return [_serialize_property(row) for row in rows]


@router.post("")
def create_property(
    req: CreatePropertyBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="name is too long (max 200 characters)")
    address = (req.address_optional or "").strip() or None
    if address and len(address) > 500:
        raise HTTPException(status_code=400, detail="address_optional is too long")

    existing_count = db.query(Property).filter(Property.user_id == current_user.id).count()
    if existing_count >= settings.FREE_TIER_MAX_PROPERTIES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limit erreicht: Maximal {settings.FREE_TIER_MAX_PROPERTIES_PER_USER} "
                "Immobilien im Free-Tarif."
            ),
        )

    property_obj = Property(
        user_id=current_user.id,
        name=name,
        address_optional=address,
    )
    db.add(property_obj)
    db.commit()
    db.refresh(property_obj)
    return _serialize_property(property_obj)


@router.get("/{property_id}")
def get_property_details(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_obj = get_owned_property_or_404(db, current_user.id, property_id)
    return _serialize_property(property_obj)


@router.patch("/{property_id}")
def update_property(
    property_id: int,
    req: PatchPropertyBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_obj = get_owned_property_or_404(db, current_user.id, property_id)

    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name must not be empty")
        if len(name) > 200:
            raise HTTPException(status_code=400, detail="name is too long (max 200 characters)")
        property_obj.name = name

    if req.address_optional is not None:
        address = req.address_optional.strip() or None
        if address and len(address) > 500:
            raise HTTPException(status_code=400, detail="address_optional is too long")
        property_obj.address_optional = address

    db.commit()
    db.refresh(property_obj)
    return _serialize_property(property_obj)


@router.delete("/{property_id}")
def delete_property(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_obj = get_owned_property_or_404(db, current_user.id, property_id)

    try:
        # Cascade: chunks → documents → timeline_items → upload_jobs → chat_messages → property
        doc_ids = [d.id for d in db.query(Document.id).filter(Document.property_id == property_obj.id).all()]
        if doc_ids:
            db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(TimelineItem).filter(TimelineItem.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(UploadJob).filter(UploadJob.property_id == property_obj.id).delete(synchronize_session=False)
        db.query(ChatMessage).filter(ChatMessage.property_id == property_obj.id).delete(synchronize_session=False)
        db.delete(property_obj)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Immobilie konnte nicht gelöscht werden")

    return {"ok": True, "property_id": property_id}
