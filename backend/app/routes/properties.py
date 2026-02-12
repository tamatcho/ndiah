from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..firebase_auth import get_current_user
from ..db import get_db
from ..models import Property, User
from ..property_access import get_owned_property_or_404

router = APIRouter(prefix="/properties", tags=["properties"], dependencies=[Depends(get_current_user)])


class CreatePropertyBody(BaseModel):
    name: str
    address_optional: str | None = None


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
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "address_optional": row.address_optional,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.post("")
def create_property(
    req: CreatePropertyBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    address = (req.address_optional or "").strip() or None
    if address and len(address) > 500:
        raise HTTPException(status_code=400, detail="address_optional is too long")

    property_obj = Property(
        user_id=current_user.id,
        name=name,
        address_optional=address,
    )
    db.add(property_obj)
    db.commit()
    db.refresh(property_obj)
    return {
        "id": property_obj.id,
        "user_id": property_obj.user_id,
        "name": property_obj.name,
        "address_optional": property_obj.address_optional,
        "created_at": property_obj.created_at.isoformat() if property_obj.created_at else None,
    }


@router.get("/{property_id}")
def get_property_details(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    property_obj = get_owned_property_or_404(db, current_user.id, property_id)
    return {
        "id": property_obj.id,
        "user_id": property_obj.user_id,
        "name": property_obj.name,
        "address_optional": property_obj.address_optional,
        "created_at": property_obj.created_at.isoformat() if property_obj.created_at else None,
    }
