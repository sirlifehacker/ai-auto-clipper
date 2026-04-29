from clipper.config import Settings
from clipper.models import ClipRender, Job


class NotionLogger:
    """Logs jobs and clip metadata to a Notion database."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def log_job(self, job: Job) -> None:
        """Create or update a Notion record for the current job."""
        # TODO: Implement Notion database upsert for job-level metadata.
        raise NotImplementedError("Notion job logging is not implemented yet.")

    def log_clip(self, clip: ClipRender) -> ClipRender:
        """Create or update a Notion record for a rendered/uploaded clip."""
        # TODO: Implement Notion page creation with title, score, tags, URLs, and status.
        raise NotImplementedError("Notion clip logging is not implemented yet.")
