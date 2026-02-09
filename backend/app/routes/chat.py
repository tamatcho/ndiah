from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..rag import search, answer_with_context
from ..config import settings

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatRequest(BaseModel):
    question: str

@router.post("")
def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        contexts = search(question, settings.FAISS_DIR, k=6)
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
