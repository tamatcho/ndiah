from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..extractors import extract_timeline

router = APIRouter(prefix="/timeline", tags=["timeline"])

class TimelineRequest(BaseModel):
    raw_text: str

@router.post("/extract")
def timeline_extract(req: TimelineRequest):
    raw_text = req.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    try:
        result = extract_timeline(raw_text)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Timeline extraction failed")

    return result.model_dump()
