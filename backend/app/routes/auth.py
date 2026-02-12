from fastapi import APIRouter, Depends

from ..firebase_auth import CurrentUserContext, get_current_user_context

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(current: CurrentUserContext = Depends(get_current_user_context)):
    return {
        "id": current.db_user.id,
        "uid": current.uid,
        "email": current.email,
        "created_at": current.db_user.created_at.isoformat() if current.db_user.created_at else None,
    }
