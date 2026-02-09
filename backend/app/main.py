import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import Base, engine
from .config import settings
from .routes import documents, chat, timeline

def ensure_storage_paths() -> None:
    for path in (settings.STORAGE_DIR, settings.UPLOAD_DIR, settings.FAISS_DIR):
        os.makedirs(path, exist_ok=True)


ensure_storage_paths()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Property AI MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def validate_settings():
    if not settings.OPENAI_API_KEY.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Set it in backend/.env before starting the API."
        )

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(timeline.router)

@app.get("/health")
def health():
    return {"ok": True}
