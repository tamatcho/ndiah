import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(status_code=400, detail="Invalid email")
    return normalized


def hash_login_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_magic_token() -> str:
    return secrets.token_urlsafe(32)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _session_secret() -> bytes:
    secret = settings.SESSION_SECRET.strip()
    if not secret:
        raise HTTPException(status_code=500, detail="SESSION_SECRET is not configured")
    return secret.encode("utf-8")


def create_session_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user_id,
        "exp": int((now + timedelta(seconds=settings.SESSION_TTL_SECONDS)).timestamp()),
        "iat": int(now.timestamp()),
        "nonce": secrets.token_urlsafe(8),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64url_encode(payload_bytes)
    sig = hmac.new(_session_secret(), payload_part.encode("utf-8"), hashlib.sha256).digest()
    signature_part = _b64url_encode(sig)
    return f"{payload_part}.{signature_part}"


def _verify_session_token(token: str) -> dict:
    parts = (token or "").split(".")
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="Invalid session")

    payload_part, signature_part = parts
    expected_sig = hmac.new(_session_secret(), payload_part.encode("utf-8"), hashlib.sha256).digest()
    try:
        got_sig = _b64url_decode(signature_part)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    if not hmac.compare_digest(got_sig, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid session")

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    exp = payload.get("exp")
    uid = payload.get("uid")
    if not isinstance(exp, int) or not isinstance(uid, int):
        raise HTTPException(status_code=401, detail="Invalid session")
    if exp <= int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="Session expired")
    return payload


def get_current_user(
    session_cookie: str | None = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    if not session_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = _verify_session_token(session_cookie)
    user = db.query(User).filter(User.id == payload["uid"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session user")
    return user
