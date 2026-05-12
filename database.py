from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./epstein_jobs.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DocumentJob(Base):
    __tablename__ = "document_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(String, unique=True, index=True, nullable=False)  # e.g. courtlistener filename or sha256
    source_url = Column(String, nullable=False)
    filename = Column(String)
    sha256 = Column(String, unique=True, index=True)
    status = Column(String, default="pending")  # pending, claimed, completed, failed
    claimed_by = Column(String, nullable=True)   # worker identifier (e.g. hostname or token)
    claimed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result_url = Column(String, nullable=True)   # where the JSONL snippet was uploaded
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
