import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")  # gutes Default fürs MVP
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "text-embedding-3-large")
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "storage" / "uploads"))
    FAISS_DIR: str = os.getenv("FAISS_DIR", str(BASE_DIR / "storage" / "faiss"))
    DB_URL: str = os.getenv("DB_URL", "sqlite:///./storage/app.db")

settings = Settings()