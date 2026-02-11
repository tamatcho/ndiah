from sqlalchemy.orm import Session

from .extractors import extract_timeline
from .models import Document, TimelineItem
from .pdf_ingest import extract_text_from_pdf


def extract_and_store_timeline_for_document(
    db: Session, doc: Document, raw_text: str | None = None
) -> list[dict]:
    text = raw_text if raw_text is not None else extract_text_from_pdf(doc.path)
    if not (text or "").strip():
        return []

    result = extract_timeline(text)
    items = [item.model_dump() for item in result.items]

    db.query(TimelineItem).filter(TimelineItem.document_id == doc.id).delete(
        synchronize_session=False
    )
    if items:
        db.add_all(
            [
                TimelineItem(
                    document_id=doc.id,
                    title=item["title"],
                    date_iso=item["date_iso"],
                    time_24h=item.get("time_24h"),
                    category=item["category"],
                    amount_eur=item.get("amount_eur"),
                    description=item["description"],
                )
                for item in items
            ]
        )
    return items
