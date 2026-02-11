from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
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


class TimelineItem(Base):
    __tablename__ = "timeline_items"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    date_iso = Column(String, nullable=False)
    time_24h = Column(String, nullable=True)
    category = Column(String, nullable=False)
    amount_eur = Column(Float, nullable=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
