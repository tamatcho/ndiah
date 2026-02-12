import json
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
except ModuleNotFoundError:  # pragma: no cover - depends on runtime env
    firebase_admin = None
    firebase_auth = None
    credentials = None


@dataclass
class CurrentUserContext:
    db_user: User
    uid: str
    email: str


def _uid_storage_key(uid: str) -> str:
    return f"firebase_uid:{uid}"


def _ensure_firebase_sdk() -> None:
    if firebase_admin is None or firebase_auth is None or credentials is None:
        raise RuntimeError(
            "Firebase Admin SDK is not installed. Install dependency 'firebase-admin'."
        )


def _build_firebase_credential() -> object:
    _ensure_firebase_sdk()
    raw_json = (settings.FIREBASE_SERVICE_ACCOUNT_JSON or "").strip()
    file_path = (settings.FIREBASE_SERVICE_ACCOUNT_FILE or "").strip()

    if raw_json:
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        return credentials.Certificate(info)

    if file_path:
        return credentials.Certificate(file_path)

    raise RuntimeError(
        "Firebase Admin is not configured. Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_FILE."
    )


@lru_cache(maxsize=1)
def _firebase_app() -> object:
    _ensure_firebase_sdk()
    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred = _build_firebase_credential()
    return firebase_admin.initialize_app(cred)


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    return parts[1].strip()


def get_current_user_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> CurrentUserContext:
    token = _extract_bearer_token(authorization)

    try:
        _firebase_app()
        decoded = firebase_auth.verify_id_token(token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token")

    uid = str(decoded.get("uid") or "").strip()
    email = str(decoded.get("email") or "").strip().lower()
    if not uid:
        raise HTTPException(status_code=401, detail="Firebase token has no uid")

    user_lookup_key = _uid_storage_key(uid)
    db_user = db.query(User).filter(User.email == user_lookup_key).first()
    if not db_user:
        db_user = User(email=user_lookup_key)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    return CurrentUserContext(db_user=db_user, uid=uid, email=email)


def get_current_user(
    context: CurrentUserContext = Depends(get_current_user_context),
) -> User:
    return context.db_user
