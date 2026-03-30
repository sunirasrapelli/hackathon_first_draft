"""
In-memory job store for background analysis tasks.

Each job has:
  - id:       UUID string
  - status:   queued | running | done | error
  - progress: list of step messages shown to the user in real-time
  - files:    {"excel": path, "report": path} once done
  - error:    error message string if status == "error"
"""
import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional


class Job:
    def __init__(self, job_id: str):
        self.id        = job_id
        self.status: Literal["queued", "running", "done", "error"] = "queued"
        self.progress: List[dict] = []   # [{step, message, done}]
        self.files: Dict[str, str] = {}  # {"excel": path, "report": path}
        self.error: Optional[str]  = None
        self.created_at            = datetime.now().isoformat()
        self.finished_at: Optional[str] = None

    def log(self, step: str, message: str, done: bool = False):
        self.progress.append({"step": step, "message": message, "done": done})

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "status":      self.status,
            "progress":    self.progress,
            "files":       {k: True for k in self.files},  # don't expose server paths
            "error":       self.error,
            "created_at":  self.created_at,
            "finished_at": self.finished_at,
        }


# Global in-memory store  (survives the request but not server restart)
_store: Dict[str, Job] = {}


def create_job() -> Job:
    job_id = str(uuid.uuid4())
    job = Job(job_id)
    _store[job_id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _store.get(job_id)
