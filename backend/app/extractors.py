import json
import re
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from .config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


CATEGORY_PRIORITY = {"deadline": 0, "payment": 1, "meeting": 2, "info": 3}


class TimelineItem(BaseModel):
    title: str
    date_iso: str = Field(description="YYYY-MM-DD")
    time_24h: Optional[str] = Field(default=None, description="HH:MM")
    category: Literal["meeting", "payment", "deadline", "info"]
    amount_eur: Optional[float] = None
    description: str
    source_quote: Optional[str] = Field(
        default=None,
        max_length=160,
        description="Kurzes Originalzitat aus dem Text (max 160 Zeichen)",
    )


    @field_validator("date_iso")
    @classmethod
    def validate_date_iso(cls, value: str) -> str:
        # Enforce precise calendar dates and reject month-only style values.
        datetime.strptime(value, "%Y-%m-%d")
        return value

class TimelineExtraction(BaseModel):
    items: List[TimelineItem]


def _extract_json_payload(content: str) -> dict:
    normalized = (content or "").strip()
    if not normalized:
        raise ValueError("empty_response")

    # Some models still wrap JSON in markdown fences despite json_object mode.
    if normalized.startswith("```"):
        normalized = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", normalized)
        normalized = re.sub(r"\s*```$", "", normalized)

    data = json.loads(normalized)
    if isinstance(data, list):
        return {"items": data}
    if not isinstance(data, dict):
        raise ValueError("invalid_json_root")

    items = data.get("items")
    if isinstance(items, list):
        return {"items": items}

    for alias in ("timeline", "events", "entries", "results"):
        alias_items = data.get(alias)
        if isinstance(alias_items, list):
            return {"items": alias_items}

    raise ValueError("missing_items_array")


def extract_timeline(document_text: str) -> TimelineExtraction:
    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """
Du extrahierst handlungsrelevante Ereignisse aus deutschen WEG/Immobilien-Dokumenten (Hausgeldabrechnung, Wirtschaftsplan, Einladung/Protokoll ETV, Infoblätter).
Ziel: Eine kurze Timeline, die dem Eigentümer hilft, nichts zu verpassen.

Regeln:
1) NUR Einträge mit präzisem Datum (YYYY-MM-DD). Wenn kein exaktes Datum, NICHT aufnehmen.
2) Priorisiere: deadline > payment > meeting > info. Nimm pro Dokument maximal 25 Items.
3) Schreibe title kurz (max 80 Zeichen). description 1–2 Sätze, klar und laienverständlich.
4) Beträge:
   - amount_eur nur setzen, wenn ein konkreter Eurobetrag im Text steht, sonst null.
   - Verwende Punkt als Dezimaltrennzeichen (z.B. 219.29).
5) Datum:
   - date_iso im Format YYYY-MM-DD.
   - Wenn nur Monat/Jahr angegeben: NICHT aufnehmen (zu ungenau).
6) Uhrzeit:
   - time_24h nur wenn im Text vorhanden, sonst null.
7) Kategorien:
   - meeting: Versammlung, Termin, Sitzung, Begehung
   - payment: Hausgeld, Vorschuss, Nachzahlung, Erstattung, Umlage, Rücklage-Zuführung
   - deadline: fällig bis, Frist, spätestens, Widerspruch bis, Einreichung bis
   - info: nur wenn ein konkreter Termin/Datum genannt wird, aber keine Zahlung/Frist/Meeting ist
8) Keine Spekulation: nichts erfinden, keine Annahmen.
9) source_quote:
   - Wenn möglich, gib ein kurzes direktes Zitat aus dem Text, das den Eintrag belegt.
   - Maximal 160 Zeichen.
10) Gib ausschließlich valides JSON gemäß Schema zurück.

Ausgabeformat:
{"items":[{"title":"...","date_iso":"YYYY-MM-DD","time_24h":null,"category":"meeting|payment|deadline|info","amount_eur":null,"description":"...","source_quote":"..."}]}
""",
                },
                {"role": "user", "content": document_text[:120000]},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise RuntimeError("Timeline extraction request to OpenAI failed") from e

    try:
        content = (resp.choices[0].message.content or "").strip()
        data = _extract_json_payload(content)
        valid_items: List[TimelineItem] = []
        for raw_item in data.get("items", []):
            try:
                valid_items.append(TimelineItem.model_validate(raw_item))
            except Exception:
                continue
        result = TimelineExtraction(items=valid_items)
    except Exception as e:
        raise RuntimeError("Timeline extraction response parsing failed") from e

    sorted_items = sorted(
        result.items,
        key=lambda item: (
            CATEGORY_PRIORITY.get(item.category, 99),
            item.date_iso,
            item.time_24h or "99:99",
            item.title.lower(),
        ),
    )
    return TimelineExtraction(items=sorted_items[:25])
