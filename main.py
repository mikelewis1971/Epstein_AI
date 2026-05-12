from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import hashlib
import os
from datetime import datetime
from pathlib import Path
import uuid

from database import get_db, DocumentJob, engine
from schemas import JobCreate, JobResponse, ClaimJobResponse, SubmitResult

app = FastAPI(title="Epstein Document Processing Coordinator")

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

# ====================== HELPERS ======================
def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

# ====================== ROUTES ======================

@app.get("/")
def root():
    return {"message": "Epstein Distributed OCR Coordinator Running", "docs": "/docs"}

@app.post("/jobs/", response_model=JobResponse)
def create_job(job: JobCreate, db: Session = Depends(get_db)):
    existing = db.query(DocumentJob).filter(
        or_(DocumentJob.doc_id == job.doc_id, DocumentJob.sha256 == job.sha256)
    ).first()
    if existing:
        raise HTTPException(400, "Document already exists")
    
    db_job = DocumentJob(**job.model_dump())
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@app.get("/jobs/claim")
def claim_job(worker_id: str, db: Session = Depends(get_db)):
    """Worker calls this to get next available job"""
    job = db.query(DocumentJob).filter(
        DocumentJob.status == "pending"
    ).order_by(DocumentJob.created_at).first()
    
    if not job:
        raise HTTPException(404, "No pending jobs")
    
    job.status = "claimed"
    job.claimed_by = worker_id
    job.claimed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    
    return ClaimJobResponse(
        job=job,
        download_url=job.source_url
    )

@app.post("/jobs/submit")
async def submit_result(result: SubmitResult, db: Session = Depends(get_db)):
    job = db.query(DocumentJob).filter(DocumentJob.doc_id == result.doc_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    
    if job.status == "completed":
        return {"status": "already_completed"}
    
    # Save JSONL snippet
    filename = f"{job.doc_id}_{uuid.uuid4().hex[:8]}.jsonl"
    file_path = RESULTS_DIR / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.jsonl_snippet)
    
    job.status = result.status
    job.completed_at = datetime.utcnow()
    job.result_url = str(file_path)
    job.error = result.error
    db.commit()
    
    return {"status": "success", "result_file": filename}

@app.get("/jobs/pending")
def list_pending(limit: int = 50, db: Session = Depends(get_db)):
    jobs = db.query(DocumentJob).filter(DocumentJob.status == "pending").limit(limit).all()
    return jobs

@app.get("/jobs/status")
def get_status(db: Session = Depends(get_db)):
    total = db.query(DocumentJob).count()
    pending = db.query(DocumentJob).filter(DocumentJob.status == "pending").count()
    claimed = db.query(DocumentJob).filter(DocumentJob.status == "claimed").count()
    completed = db.query(DocumentJob).filter(DocumentJob.status == "completed").count()
    return {
        "total": total,
        "pending": pending,
        "claimed": claimed,
        "completed": completed
    }

# Optional: Seed some known Epstein PDFs (add more manually or via script)
@app.post("/seed-epstein")
def seed_sample_jobs(db: Session = Depends(get_db)):
    # Example using public CourtListener RECAP links
    samples = [
        {
            "doc_id": "epstein-19-cr-490-indictment",
            "source_url": "https://storage.courtlistener.com/recap/gov.uscourts.nysd.518649/gov.uscourts.nysd.518649.2.0_8.pdf",
            "filename": "epstein_indictment.pdf",
            "sha256": "placeholder"  # compute real one later
        },
        # Add more real links from CourtListener here
    ]
    added = 0
    for s in samples:
        try:
            create_job(JobCreate(**s), db)
            added += 1
        except:
            pass
    return {"added": added}
