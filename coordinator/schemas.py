from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobBase(BaseModel):
    doc_id: str
    source_url: str
    filename: str
    sha256: str

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
    jsonl_snippet: str
    status: str = "completed"
    error: Optional[str] = None
