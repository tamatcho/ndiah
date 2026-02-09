import os
import json
import numpy as np
import faiss
from openai import OpenAI
from .config import settings

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

def ensure_index(dim: int, index_path: str):
    if os.path.exists(index_path):
        try:
            return faiss.read_index(index_path)
        except Exception as e:
            raise RuntimeError("Failed to read FAISS index from disk") from e
    return faiss.IndexFlatIP(dim)

def save_meta(meta_path: str, meta: list[dict]):
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise RuntimeError("Failed to write FAISS metadata file") from e

def load_meta(meta_path: str) -> list[dict]:
    if not os.path.exists(meta_path):
        return []
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError("Failed to read FAISS metadata file") from e

def upsert_chunks(chunks: list[dict], faiss_dir: str):
    """
    chunks: [{ "chunk_id": "...", "text": "...", "document_id": 1 }]
    """
    if not chunks:
        return
    os.makedirs(faiss_dir, exist_ok=True)
    index_path = os.path.join(faiss_dir, "index.faiss")
    meta_path = os.path.join(faiss_dir, "meta.json")

    texts = [c["text"] for c in chunks]
    vecs = embed_texts(texts)
    dim = vecs.shape[1]

    index = ensure_index(dim, index_path)
    # cosine via inner product -> normalize
    faiss.normalize_L2(vecs)

    meta = load_meta(meta_path)

    # add
    index.add(vecs)
    meta.extend([{**c} for c in chunks])

    try:
        faiss.write_index(index, index_path)
    except Exception as e:
        raise RuntimeError("Failed to persist FAISS index to disk") from e
    save_meta(meta_path, meta)

def search(query: str, faiss_dir: str, k: int = 6) -> list[dict]:
    index_path = os.path.join(faiss_dir, "index.faiss")
    meta_path = os.path.join(faiss_dir, "meta.json")
    if not os.path.exists(index_path):
        return []

    try:
        index = faiss.read_index(index_path)
    except Exception as e:
        raise RuntimeError("Failed to read FAISS index from disk") from e
    meta = load_meta(meta_path)

    qv = embed_texts([query])
    faiss.normalize_L2(qv)

    k = max(1, k)
    try:
        scores, ids = index.search(qv, k)
    except Exception as e:
        raise RuntimeError("FAISS search failed") from e
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        item = meta[idx]
        results.append({"score": float(score), **item})
    return results

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
