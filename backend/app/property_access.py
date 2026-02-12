from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Property


def get_owned_property_or_404(db: Session, user_id: int, property_id: int) -> Property:
    property_obj = (
        db.query(Property)
        .filter(Property.id == property_id, Property.user_id == user_id)
        .first()
    )
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    return property_obj
