from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime
from .db import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True, nullable=False)
    chunk_id = Column(String, index=True)
    text = Column(Text, nullable=False)
