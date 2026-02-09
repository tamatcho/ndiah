from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

connect_args = {}
if settings.DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
