import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clipper.config import Settings, get_settings
from clipper.download.youtube import download_video

logger = logging.getLogger(__name__)


def download_videos_from_file(file_path: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Download each non-empty YouTube URL from a text file and write a batch manifest."""
    settings = settings or get_settings()
    settings.ensure_local_dirs()

    urls_path = Path(file_path)
    if not urls_path.exists():
        raise FileNotFoundError(f"URL input file not found: {urls_path}")

    urls = [line.strip() for line in urls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    job_id = _create_job_id()
    job_dir = Path("data/jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting download batch %s with %s URL(s)", job_id, len(urls))

    items: list[dict[str, Any]] = []
    for index, url in enumerate(urls, start=1):
        try:
            result = download_video(url, settings=settings)
            items.append(
                {
                    "index": index,
                    "url": url,
                    "metadata": result["metadata"],
                    "paths": {
                        "video": result["video_path"],
                        "metadata": result["metadata_path"],
                        "raw_dir": result["raw_dir"],
                    },
                    "processing_status": result["status"],
                }
            )
        except Exception as exc:
            logger.exception("Failed batch item %s: %s", index, url)
            items.append(
                {
                    "index": index,
                    "url": url,
                    "metadata": None,
                    "paths": {},
                    "processing_status": "failed",
                    "error": str(exc),
                }
            )

    manifest = {
        "job_id": job_id,
        "created_at": datetime.now(UTC).isoformat(),
        "input_file": str(urls_path),
        "items": items,
    }
    manifest_path = job_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved batch manifest to %s", manifest_path)

    return items


def _create_job_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
