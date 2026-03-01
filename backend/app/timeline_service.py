from sqlalchemy.orm import Session

from .extractors import extract_timeline
from .models import Document, TimelineItem
from .pdf_ingest import extract_text_from_pdf, extract_text_from_pdf_bytes


def extract_and_store_timeline_for_document(
    db: Session, doc: Document, raw_text: str | None = None
) -> list[dict]:
    if raw_text is not None:
        text = raw_text
    elif doc.extracted_text:
        text = doc.extracted_text
    elif doc.file_bytes:
        text = extract_text_from_pdf_bytes(doc.file_bytes)
    elif doc.path:
        text = extract_text_from_pdf(doc.path)
    else:
        text = ""
    if not (text or "").strip():
        return []

    result = extract_timeline(text)
    items = [item.model_dump() for item in result.items]

    # Deduplicate within this extraction result: keep the item with the richer description
    seen: dict[tuple, dict] = {}
    for item in items:
        key = (item["date_iso"], item["title"].strip().lower())
        existing = seen.get(key)
        if existing is None or len(item.get("description", "")) > len(existing.get("description", "")):
            seen[key] = item
    items = list(seen.values())

    # Skip items that already exist in the DB for this property from a different document
    if items:
        existing_rows = (
            db.query(TimelineItem.date_iso, TimelineItem.title)
            .filter(
                TimelineItem.property_id == doc.property_id,
                TimelineItem.document_id != doc.id,
            )
            .all()
        )
        existing_keys = {(row.date_iso, row.title.strip().lower()) for row in existing_rows}
        items = [
            item for item in items
            if (item["date_iso"], item["title"].strip().lower()) not in existing_keys
        ]

    db.query(TimelineItem).filter(TimelineItem.document_id == doc.id).delete(
        synchronize_session=False
    )
    if items:
        db.add_all(
            [
                TimelineItem(
                    document_id=doc.id,
                    property_id=doc.property_id,
                    title=item["title"],
                    date_iso=item["date_iso"],
                    time_24h=item.get("time_24h"),
                    category=item["category"],
                    amount_eur=item.get("amount_eur"),
                    description=item["description"],
                    source_quote=item.get("source_quote"),
                )
                for item in items
            ]
        )
    return items
