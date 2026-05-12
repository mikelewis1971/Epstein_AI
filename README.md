# Epstein_AI
Turn the Epstien files into an AI by converting the documents to a RAG or training data


**Here's the refactored, no-bullshit, LM Studio-centric guide.** Everything is built around LM Studio's local OpenAI-compatible server for maximum simplicity and compatibility with your Qwen workflow.

### 1. Install and Set Up LM Studio (Exact Steps)
1. Go to [lmstudio.ai](https://lmstudio.ai/) and download the latest version for your OS (Windows, macOS, or Linux).
2. Install and open LM Studio.
3. **Download the Vision Model** (required for OCR/transcription):
   - Go to the **Discover** / search tab.
   - Search for: `Qwen2.5-VL-7B-Instruct` (recommended) or the smaller `Qwen2.5-VL-3B` / `2B` variants if VRAM is limited.
   - Download a GGUF quantized version (e.g., Q4_K_M or Q5_K_M for good speed/quality balance). LM Studio will show available quants.
   - Load the model in the chat interface first and test it with a sample document image to confirm vision works ("Transcribe this page").

4. **Start the Local Server** (this is what your Python scripts will talk to):
   - Click the **Developer** tab (bottom-left or sidebar).
   - Toggle **Developer Mode** if needed.
   - In the Developer/Local Server section, turn on the server (Status: Running).
   - Default endpoint: `http://localhost:1234/v1`
   - You can also use the CLI: `lms server start` in a terminal.

**Test the server** (optional but recommended):
```bash
curl http://localhost:1234/v1/models
```

### 2. Python Environment Setup
```bash
# Create a clean environment
python -m venv epstein_pipeline
source epstein_pipeline/bin/activate    # Windows: epstein_pipeline\Scripts\activate

pip install openai pymupdf pillow requests tqdm sqlite3  # PyMuPDF = fitz
```

### 3. Core Worker Script (LM Studio + Multi-Pass OCR)
This script uses your local LM Studio server for all vision calls. Save as `worker.py`.

```python
import fitz  # PyMuPDF
import base64
import hashlib
import json
from pathlib import Path
from openai import OpenAI
from tqdm import tqdm
import time

# Point to LM Studio
client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"  # dummy key, LM Studio ignores it
)

MODEL_NAME = "qwen2.5-vl-7b-instruct"  # exact name as loaded in LM Studio

def image_to_base64(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

def process_page(page_pixmap, page_num, doc_name):
    img_bytes = page_pixmap.tobytes("png")
    b64 = image_to_base64(img_bytes)
    
    transcripts = []
    temperatures = [0.2, 0.5, 0.7]
    
    for temp in temperatures:
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Accurately transcribe ALL text from this document page. Include layout, handwriting, redactions, and any notes. Be precise and complete."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ]
                }],
                temperature=temp,
                max_tokens=4096
            )
            transcripts.append(response.choices[0].message.content.strip())
            time.sleep(0.5)  # gentle rate limit
        except Exception as e:
            print(f"Error on temp {temp}: {e}")
            transcripts.append("")
    
    # Consensus / synthesis pass (send image + all 3 transcripts)
    consensus_prompt = f"""You are an expert document transcriber.
Here are 3 independent transcriptions of the same page.
Compare them carefully, resolve differences, correct errors, and produce ONE final high-quality transcription.

Transcripts:
1. {transcripts[0]}
2. {transcripts[1]}
3. {transcripts[2]}
"""
    
    final_resp = client.chat.completions.create(
        model=MODEL_NAME,  # or switch to a strong text-only Qwen if you prefer
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": consensus_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        temperature=0.3
    )
    
    final_text = final_resp.choices[0].message.content.strip()
    
    return {
        "source": doc_name,
        "page": page_num + 1,
        "text": final_text,
        "transcripts_raw": transcripts  # for debugging
    }

def main():
    pdf_folder = Path("pdfs")
    output_file = Path("training_data.jsonl")
    
    for pdf_path in tqdm(list(pdf_folder.glob("*.pdf"))):
        doc_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        # TODO: check against central DB to skip duplicates
        
        doc = fitz.open(pdf_path)
        results = []
        
        for i in range(len(doc)):
            pix = doc[i].get_pixmap(dpi=250)  # 200-300 DPI good for docs
            page_data = process_page(pix, i, pdf_path.name)
            results.append(page_data)
        
        # Append to JSONL
        with output_file.open("a", encoding="utf-8") as f:
            for res in results:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
        
        print(f"Processed {pdf_path.name} — {len(doc)} pages")

if __name__ == "__main__":
    main()
```

--------------------------------

**✅ Full FastAPI Coordinator Code** (LM Studio-native, production-ready starter)

This is a complete, self-contained FastAPI application for your distributed Epstein document processing project.

### Project Structure
```
epstein-coordinator/
├── main.py
├── database.py
├── models.py
├── schemas.py
├── worker_client.py      # optional helper
├── requirements.txt
└── README.md
```

### 1. `requirements.txt`
```txt
fastapi==0.115.*
uvicorn[standard]
sqlalchemy
alembic
pydantic==2.*
python-dotenv
requests
python-multipart
httpx
```

Install with: `pip install -r requirements.txt`

### 2. `database.py`
```python
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
```

### 3. `schemas.py`
```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class JobBase(BaseModel):
    doc_id: str
    source_url: str
    filename: str
    sha256: str

class JobCreate(JobBase):
    pass

class JobResponse(JobBase):
    id: int
    status: str
    claimed_by: Optional[str]
    claimed_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ClaimJobResponse(BaseModel):
    job: JobResponse
    download_url: str

class SubmitResult(BaseModel):
    doc_id: str
    worker_id: str
    jsonl_snippet: str   # or list of page dicts; we'll save to file
    status: str = "completed"
    error: Optional[str] = None
```

### 4. `main.py` (Full FastAPI App)
```python
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
```

### How to Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Access at: `http://your-server:8000/docs` (interactive Swagger UI)

### Worker Usage Example
```python
import requests

WORKER_ID = "node-01-mikes-gpu"

# Claim job
resp = requests.get(f"http://mikes_server.com:8000/jobs/claim?worker_id={WORKER_ID}")
if resp.status_code == 200:
    data = resp.json()
    job = data["job"]
    pdf_url = data["download_url"]
    
    # Download PDF → process with your worker.py (LM Studio) → get jsonl_snippet
    # ...
    
    submit_data = {
        "doc_id": job["doc_id"],
        "worker_id": WORKER_ID,
        "jsonl_snippet": open("processed.jsonl").read(),
        "status": "completed"
    }
    requests.post("http://mikes_server.com:8000/jobs/submit", json=submit_data)
```



Want me to generate the full coordinator FastAPI code, deduplication DB script, or a polished HTML user guide next? Just say the word. This setup is solid, local-first, and scales with many hands.
