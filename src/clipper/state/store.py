import json
from pathlib import Path

from clipper.config import Settings
from clipper.models import Job


class JobStore:
    """Persists local job state for resume, preview, and auditing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(self, urls: list[str]) -> Job:
        job = Job(urls=urls)
        self.save(job)
        return job

    def save(self, job: Job) -> None:
        """Persist the current job state."""
        # TODO: Add SQLite backend when querying and migrations become important.
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._job_path(job.id).write_text(json.dumps(self._serialize_job(job), indent=2), encoding="utf-8")

    def get(self, job_id: str) -> Job:
        """Load a job by id."""
        payload = json.loads(self._job_path(job_id).read_text(encoding="utf-8"))
        return self._deserialize_job(payload)

    def list_recent(self, limit: int = 20) -> list[Job]:
        """Return recent jobs for the Streamlit review UI."""
        if not self._jobs_dir.exists():
            return []
        paths = sorted(self._jobs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return [self.get(path.stem) for path in paths[:limit]]

    @property
    def _jobs_dir(self) -> Path:
        return Path("data/jobs")

    def _job_path(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_id}.json"

    def _serialize_job(self, job: Job) -> dict:
        return job.model_dump(mode="json")

    def _deserialize_job(self, payload: dict) -> Job:
        return Job.model_validate(payload)
