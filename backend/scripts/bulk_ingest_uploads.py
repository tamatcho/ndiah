import os
import sys
import argparse
from typing import List

# Allow running this file directly from backend/ via:
# python scripts/bulk_ingest_uploads.py
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Document, Property
from app.pdf_ingest import extract_text_from_pdf, simple_chunk
from app.rag import upsert_chunks


def list_pdf_paths(upload_dir: str) -> List[str]:
    if not os.path.isdir(upload_dir):
        return []
    paths = []
    for name in sorted(os.listdir(upload_dir)):
        path = os.path.join(upload_dir, name)
        if os.path.isfile(path) and name.lower().endswith(".pdf"):
            paths.append(path)
    return paths


def _ingest_pdf(db, pdf_path: str, reindex: bool, property_id: int) -> tuple[bool, bool]:
    """
    Returns:
    - (processed, was_skipped)
    """
    filename = os.path.basename(pdf_path)
    existing = db.query(Document).filter(Document.path == pdf_path).first()

    if existing and not reindex:
        print(f"SKIP (exists): {filename}")
        return False, True

    created_doc = False
    doc = existing
    if doc is None:
        doc = Document(filename=filename, path=pdf_path, property_id=property_id)
        db.add(doc)
        db.flush()
        created_doc = True

    text = extract_text_from_pdf(pdf_path)
    doc.extracted_text = text
    chunks = simple_chunk(text, with_metadata=True)
    payload = [
        {
            "document_id": doc.id,
            "chunk_id": f"{doc.id}-p{int(ch['page'])}-{int(ch['page_chunk_index'])}",
            "text": str(ch["text"]),
        }
        for ch in chunks
    ]
    upsert_chunks(db, payload)
    if created_doc:
        db.commit()
    print(f"OK: {filename} -> {len(payload)} chunks")
    return True, False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk ingest PDFs from UPLOAD_DIR into DB."
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Recompute chunk embeddings from all PDFs in UPLOAD_DIR (ignores skip-by-existing behavior).",
    )
    parser.add_argument(
        "--property-id",
        type=int,
        required=True,
        help="Property ID that will own ingested documents.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    Base.metadata.create_all(bind=engine)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    db = SessionLocal()
    total = 0
    ingested = 0
    skipped_existing = 0
    failed = 0

    try:
        if not db.query(Property).filter(Property.id == args.property_id).first():
            raise RuntimeError(f"Property {args.property_id} does not exist")
        if args.reindex:
            print("Reindex mode: recomputing chunk embeddings.")

        for pdf_path in list_pdf_paths(settings.UPLOAD_DIR):
            total += 1
            try:
                processed, skipped = _ingest_pdf(db, pdf_path, reindex=args.reindex, property_id=args.property_id)
                if skipped:
                    skipped_existing += 1
                if processed:
                    ingested += 1
            except Exception as e:
                db.rollback()
                failed += 1
                filename = os.path.basename(pdf_path)
                print(f"FAIL: {filename} -> {e}")
    finally:
        db.close()

    print("")
    print("Summary")
    print(f"Total PDFs found: {total}")
    print(f"Ingested: {ingested}")
    print(f"Skipped (already in DB): {skipped_existing}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
