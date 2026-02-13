import json
import numpy as np
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .models import Chunk, Document, Property

client = OpenAI(api_key=settings.OPENAI_API_KEY)


class ChatSource(BaseModel):
    document_id: int
    chunk_id: str


class ChatAnswer(BaseModel):
    answer: str
    key_points: list[str]
    sources: list[ChatSource]
    missing_info: list[str]


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


def answer_with_context(question: str, contexts: list[dict]) -> dict:
    if not contexts:
        return {
            "answer": "Im bereitgestellten Kontext wurden keine passenden Informationen gefunden.",
            "key_points": [],
            "sources": [],
            "missing_info": [f"Keine relevanten Kontextstellen zur Frage vorhanden: {question}"],
        }

    context_text = "\n\n".join(
        [f"[DOC {c['document_id']} | {c['chunk_id']}]\n{c['text']}" for c in contexts]
    )
    allowed_sources = {(int(c["document_id"]), str(c["chunk_id"])) for c in contexts}
    system_prompt = (
        "Du bist ein deutschsprachiger Assistent für Wohnungseigentümer. Nutze AUSSCHLIESSLICH den bereitgestellten Kontext.\n"
        "Wenn eine Information im Kontext nicht vorkommt, schreibe sie unter missing_info und rate nicht.\n"
        "Antworte knapp, konkret und verständlich. Zahlen/Termine nur nennen, wenn sie im Kontext stehen.\n"
        "Gib ausschließlich JSON im Format zurück:\n"
        "{\"answer\":\"...\",\"key_points\":[\"...\"],\"sources\":[{\"document_id\":number,\"chunk_id\":\"...\"}],\"missing_info\":[\"...\"]}\n"
        "Die sources sollen die DOC/Chunk Labels referenzieren, die im Kontext stehen."
    )

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"KONTEXT:\n{context_text}\n\nFRAGE:\n{question}"},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise RuntimeError("Chat completion request to OpenAI failed") from e
    try:
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        result = ChatAnswer.model_validate(data)
        filtered_sources = [
            source
            for source in result.sources
            if (int(source.document_id), str(source.chunk_id)) in allowed_sources
        ]
        return {
            "answer": result.answer,
            "key_points": result.key_points,
            "sources": [source.model_dump() for source in filtered_sources],
            "missing_info": result.missing_info,
        }
    except Exception as e:
        raise RuntimeError("Chat completion response parsing failed") from e
