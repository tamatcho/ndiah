from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import (
    create_magic_token,
    create_session_token,
    get_current_user,
    hash_login_token,
    normalize_email,
)
from ..config import settings
from ..db import get_db
from ..models import LoginToken, User

router = APIRouter(prefix="/auth", tags=["auth"])


class RequestLinkBody(BaseModel):
    email: str


@router.post("/request-link")
def request_link(req: RequestLinkBody, db: Session = Depends(get_db)):
    email = normalize_email(req.email)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    raw_token = create_magic_token()
    token_hash = hash_login_token(raw_token)
    expiry = datetime.utcnow() + timedelta(minutes=settings.MAGIC_LINK_TTL_MINUTES)
    db.add(LoginToken(user_id=user.id, token_hash=token_hash, expires_at=expiry))
    db.commit()

    resp = {"ok": True}
    if settings.ENV == "DEV":
        resp["magic_link"] = f"/auth/verify?token={raw_token}"
    return resp


@router.get("/verify")
def verify_magic_link(token: str, response: Response, db: Session = Depends(get_db)):
    token_hash = hash_login_token(token)
    now = datetime.utcnow()
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token_hash == token_hash)
        .filter(LoginToken.used_at.is_(None))
        .filter(LoginToken.expires_at > now)
        .first()
    )
    if not login_token:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == login_token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token user")

    login_token.used_at = now
    db.commit()

    session_token = create_session_token(user.id)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=settings.ENV != "DEV",
        samesite="lax",
        max_age=settings.SESSION_TTL_SECONDS,
    )
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.ENV != "DEV",
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }
