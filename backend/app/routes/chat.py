from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..property_access import get_owned_property_or_404
from ..rag import search, answer_with_context
from sqlalchemy.orm import Session

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])

class ChatRequest(BaseModel):
    question: str
    property_id: int | None = None

@router.post("")
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    if req.property_id is not None:
        get_owned_property_or_404(db, current_user.id, req.property_id)

    try:
        contexts = search(question, db=db, user_id=current_user.id, property_id=req.property_id, k=6)
        answer = answer_with_context(question, contexts)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Chat request failed")

    return {
        "answer": answer,
        "sources": [
            {"document_id": c["document_id"], "chunk_id": c["chunk_id"], "score": c["score"]}
            for c in contexts
        ],
    }
