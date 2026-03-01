import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Literal
from ..firebase_auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import ChatMessage, User
from ..property_access import get_owned_property_or_404
from ..rag import search, answer_with_context
from ..rate_limit import limiter
from sqlalchemy.orm import Session

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])

class ChatRequest(BaseModel):
    question: str
    property_id: int | None = None
    language: Literal["de", "en", "fr"] = "de"

@router.post("")
@limiter.limit(settings.CHAT_RATE_LIMIT)
def chat(
    request: Request,
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="Frage zu lang (max. 2000 Zeichen).")
    if req.property_id is not None:
        get_owned_property_or_404(db, current_user.id, req.property_id)

    try:
        contexts = search(question, db=db, user_id=current_user.id, property_id=req.property_id, k=6)
        answer_json = answer_with_context(question, contexts, language=req.language)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Chat request failed")

    # Save user question and assistant answer to DB (best-effort — never fail the response)
    try:
        db.add(ChatMessage(
            user_id=current_user.id,
            property_id=req.property_id,
            role="user",
            text=question,
        ))
        db.add(ChatMessage(
            user_id=current_user.id,
            property_id=req.property_id,
            role="assistant",
            text=answer_json["answer"],
            sources_json=json.dumps(answer_json.get("sources", []), ensure_ascii=False),
        ))
        db.commit()
    except Exception:
        db.rollback()

    return answer_json


@router.get("/history")
def chat_history(
    property_id: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if property_id is not None:
        get_owned_property_or_404(db, current_user.id, property_id)
    query = db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id)
    if property_id is not None:
        query = query.filter(ChatMessage.property_id == property_id)
    else:
        query = query.filter(ChatMessage.property_id.is_(None))
    messages = query.order_by(ChatMessage.created_at.asc()).limit(max(1, min(limit, 500))).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "text": m.text,
            "sources": json.loads(m.sources_json) if m.sources_json else [],
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.delete("/history")
def clear_chat_history(
    property_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if property_id is not None:
        get_owned_property_or_404(db, current_user.id, property_id)
    query = db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id)
    if property_id is not None:
        query = query.filter(ChatMessage.property_id == property_id)
    else:
        query = query.filter(ChatMessage.property_id.is_(None))
    deleted = query.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
