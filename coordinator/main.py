from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime
from pathlib import Path
import hashlib
import uuid

from database import get_db, DocumentJob
from schemas import JobBase, JobResponse, ClaimJobResponse, SubmitResult

app = FastAPI(title="Epstein DOJ Document Coordinator")

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

@app.get("/")
def root():
    return {"message": "Epstein AI Coordinator Running"}

@app.post("/jobs/", response_model=JobResponse)
def create_job(job: JobBase, db: Session = Depends(get_db)):
    existing = db.query(DocumentJob).filter(
        or_(DocumentJob.doc_id == job.doc_id, DocumentJob.sha256 == job.sha256)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Document already exists")
    
    db_job = DocumentJob(**job.model_dump())
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@app.get("/jobs/claim")
def claim_job(worker_id: str, db: Session = Depends(get_db)):
    job = db.query(DocumentJob).filter(DocumentJob.status == "pending").first()
    if not job:
        raise HTTPException(status_code=404, detail="No pending jobs")
    
    job.status = "claimed"
    job.claimed_by = worker_id
    job.claimed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    
    return ClaimJobResponse(job=job, download_url=job.source_url)

@app.post("/jobs/submit")
def submit_result(result: SubmitResult, db: Session = Depends(get_db)):
    job = db.query(DocumentJob).filter(DocumentJob.doc_id == result.doc_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status == "completed":
        return {"status": "already_completed"}
    
    filename = f"{job.doc_id}_{uuid.uuid4().hex[:8]}.jsonl"
    file_path = RESULTS_DIR / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.jsonl_snippet)
    
    job.status = result.status
    job.completed_at = datetime.utcnow()
    job.result_path = str(file_path)
    job.error = result.error
    db.commit()
    
    return {"status": "success", "result_file": filename}

@app.get("/jobs/status")
def get_status(db: Session = Depends(get_db)):
    total = db.query(DocumentJob).count()
    pending = db.query(DocumentJob).filter(DocumentJob.status == "pending").count()
    claimed = db.query(DocumentJob).filter(DocumentJob.status == "claimed").count()
    completed = db.query(DocumentJob).filter(DocumentJob.status == "completed").count()
    return {"total": total, "pending": pending, "claimed": claimed, "completed": completed}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
