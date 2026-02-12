import json
import numpy as np
from openai import OpenAI
from sqlalchemy.orm import Session

from .config import settings
from .models import Chunk, Document, Property

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype="float32")
    try:
        resp = client.embeddings.create(model=settings.EMBED_MODEL, input=texts)
    except Exception as e:
        raise RuntimeError("Embedding request to OpenAI failed") from e
    vecs = [d.embedding for d in resp.data]
    return np.array(vecs, dtype="float32")


def upsert_chunks(db: Session, chunks: list[dict]):
    """
    chunks: [{ "document_id": 1, "chunk_id": "1-0", "text": "..." }]
    """
    if not chunks:
        return
    texts = [c["text"] for c in chunks]
    vecs = embed_texts(texts)

    doc_id = chunks[0]["document_id"]
    db.query(Chunk).filter(Chunk.document_id == doc_id).delete(synchronize_session=False)
    for chunk, vec in zip(chunks, vecs):
        db.add(
            Chunk(
                document_id=chunk["document_id"],
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                embedding_json=json.dumps(vec.tolist(), ensure_ascii=False),
            )
        )


def _cosine_similarity(query_vec: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        return np.zeros((embeddings.shape[0],), dtype=np.float32)
    emb_norms = np.linalg.norm(embeddings, axis=1)
    denom = emb_norms * q_norm
    denom[denom == 0] = 1e-12
    return (embeddings @ query_vec) / denom


def search(query: str, db: Session, user_id: int, property_id: int | None = None, k: int = 6) -> list[dict]:
    qv = embed_texts([query])
    if qv.size == 0:
        return []
    query_vec = qv[0]

    sql = (
        db.query(Chunk, Document.property_id)
        .join(Document, Chunk.document_id == Document.id)
        .join(Property, Document.property_id == Property.id)
        .filter(Property.user_id == user_id)
    )
    if property_id is not None:
        sql = sql.filter(Document.property_id == property_id)
    rows = sql.all()
    if not rows:
        return []

    candidates: list[dict] = []
    vectors: list[list[float]] = []
    for chunk, doc_property_id in rows:
        if not chunk.embedding_json:
            continue
        try:
            vectors.append(json.loads(chunk.embedding_json))
        except Exception:
            continue
        candidates.append(
            {
                "document_id": chunk.document_id,
                "property_id": doc_property_id,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
            }
        )
    if not candidates:
        return []

    emb_matrix = np.array(vectors, dtype=np.float32)
    scores = _cosine_similarity(query_vec, emb_matrix)
    top_k = max(1, k)
    best_idx = np.argsort(scores)[::-1][:top_k]
    return [{**candidates[i], "score": float(scores[i])} for i in best_idx]


def answer_with_context(question: str, contexts: list[dict]) -> str:
    context_text = "\n\n".join(
        [f"[DOC {c['document_id']} | {c['chunk_id']}]\n{c['text']}" for c in contexts]
    )
    prompt = (
        "Du bist ein deutschsprachiger Assistent für Wohnungseigentümer.\n"
        "Nutze NUR den Kontext aus den Dokumenten. Wenn etwas nicht im Kontext steht, sag es ehrlich.\n"
        "Antworte klar, mit konkreten Zahlen/Terminen, und erkläre Fachbegriffe einfach.\n\n"
        f"KONTEXT:\n{context_text}\n\nFRAGE:\n{question}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Antworte auf Deutsch."},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as e:
        raise RuntimeError("Chat completion request to OpenAI failed") from e
    text = (resp.choices[0].message.content or "").strip()
    return text
