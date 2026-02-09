import json
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional
from .config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

class TimelineItem(BaseModel):
    title: str
    date_iso: str = Field(description="YYYY-MM-DD")
    time_24h: Optional[str] = Field(default=None, description="HH:MM")
    category: str = Field(description="meeting|payment|deadline|info")
    amount_eur: Optional[float] = None
    description: str

class TimelineExtraction(BaseModel):
    items: List[TimelineItem]

def extract_timeline(document_text: str) -> TimelineExtraction:
    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extrahiere aus dem Text Termine, Fristen, Zahlungszeitpunkte und relevante Beträge. "
                        "Wenn ein Datum fehlt, lasse den Eintrag weg. "
                        "Gib nur JSON zurück im Format: "
                        "{\"items\":[{\"title\":\"...\",\"date_iso\":\"YYYY-MM-DD\",\"time_24h\":\"HH:MM|null\","
                        "\"category\":\"meeting|payment|deadline|info\",\"amount_eur\":number|null,"
                        "\"description\":\"...\"}]}"
                    ),
                },
                {"role": "user", "content": document_text[:120000]},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise RuntimeError("Timeline extraction request to OpenAI failed") from e

    try:
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        return TimelineExtraction.model_validate(data)
    except Exception as e:
        raise RuntimeError("Timeline extraction response parsing failed") from e
