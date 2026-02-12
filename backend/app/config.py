import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]

class Settings:
    ENV: str = os.getenv("ENV", "DEV").upper()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")  # gutes Default fürs MVP
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "text-embedding-3-large")
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "storage" / "uploads"))
    FAISS_DIR: str = os.getenv("FAISS_DIR", str(BASE_DIR / "storage" / "faiss"))
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        os.getenv("DB_URL", f"sqlite:///{(BASE_DIR / 'storage' / 'app.db').as_posix()}"),
    )
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "dev-insecure-session-secret")
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "property_ai_session")
    SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
    MAGIC_LINK_TTL_MINUTES: int = int(os.getenv("MAGIC_LINK_TTL_MINUTES", "15"))
    MAX_PDF_BYTES: int = int(os.getenv("MAX_PDF_BYTES", str(10 * 1024 * 1024)))
    FREE_TIER_MAX_DOCUMENTS_PER_PROPERTY: int = int(
        os.getenv("FREE_TIER_MAX_DOCUMENTS_PER_PROPERTY", "50")
    )
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

settings = Settings()
