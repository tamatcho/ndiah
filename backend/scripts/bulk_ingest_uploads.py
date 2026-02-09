import os
import sys
import argparse
from typing import List

# Allow running this file directly from backend/ via:
# python scripts/bulk_ingest_uploads.py
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Document
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


def _reset_faiss_files() -> None:
    os.makedirs(settings.FAISS_DIR, exist_ok=True)
    index_path = os.path.join(settings.FAISS_DIR, "index.faiss")
    meta_path = os.path.join(settings.FAISS_DIR, "meta.json")
    for path in (index_path, meta_path):
        if os.path.exists(path):
            os.remove(path)


def _ingest_pdf(db, pdf_path: str, reindex: bool) -> tuple[bool, bool]:
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
        doc = Document(filename=filename, path=pdf_path)
        db.add(doc)
        db.flush()
        created_doc = True

    text = extract_text_from_pdf(pdf_path)
    chunks = simple_chunk(text)
    payload = [
        {"document_id": doc.id, "chunk_id": f"{doc.id}-{i}", "text": ch}
        for i, ch in enumerate(chunks)
    ]
    upsert_chunks(payload, settings.FAISS_DIR)
    if created_doc:
        db.commit()
    print(f"OK: {filename} -> {len(payload)} chunks")
    return True, False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk ingest PDFs from UPLOAD_DIR into DB + FAISS."
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild FAISS index from all PDFs in UPLOAD_DIR (ignores skip-by-existing behavior).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    Base.metadata.create_all(bind=engine)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.FAISS_DIR, exist_ok=True)

    if args.reindex:
        _reset_faiss_files()
        print("Reindex mode: cleared existing FAISS index/meta files.")

    db = SessionLocal()
    total = 0
    ingested = 0
    skipped_existing = 0
    failed = 0

    try:
        for pdf_path in list_pdf_paths(settings.UPLOAD_DIR):
            total += 1
            try:
                processed, skipped = _ingest_pdf(db, pdf_path, reindex=args.reindex)
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
