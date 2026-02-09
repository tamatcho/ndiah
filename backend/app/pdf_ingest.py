import os
from pypdf import PdfReader

def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts = []
    for i, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        parts.append(f"\n\n--- PAGE {i+1} ---\n{txt}")
    return "\n".join(parts)

def simple_chunk(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    text = text.strip()
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= max_chars:
        overlap = max_chars // 4
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0
        if end == len(text):
            break
    return chunks
