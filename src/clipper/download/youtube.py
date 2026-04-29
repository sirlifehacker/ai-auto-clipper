import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from clipper.config import Settings
from clipper.models import SourceVideo

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, float | None], None]


class YouTubeDownloader:
    """Downloads YouTube videos and returns normalized source metadata."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def download(self, url: str) -> SourceVideo:
        """Download a single YouTube URL and return source video metadata."""
        result = download_video(url, settings=self.settings)
        metadata = result["metadata"]
        return SourceVideo(
            url=metadata["original_url"],
            video_id=metadata["video_id"],
            title=metadata["title"],
            duration_seconds=metadata["duration"],
            local_path=Path(result["video_path"]),
        )

    def _build_output_template(self) -> Path:
        return self.settings.raw_dir / "%(id)s" / "source.%(ext)s"


def download_video(
    url: str,
    settings: Settings | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Download one YouTube video and persist its source file and metadata."""
    from clipper.config import get_settings

    settings = settings or get_settings()
    settings.ensure_local_dirs()

    try:
        if progress_callback:
            progress_callback("Fetching YouTube metadata", None)
        info = _extract_info(url, settings)
        video_id = _require_video_id(info, url)
        video_dir = settings.raw_dir / video_id
        video_path = video_dir / "source.mp4"
        metadata_path = video_dir / "metadata.json"

        video_dir.mkdir(parents=True, exist_ok=True)
        metadata = _build_metadata(info, url, video_id)
        _recover_legacy_nested_download(settings, video_id, video_path)
        existed_before = video_path.exists()

        if existed_before:
            logger.info("Skipping download for %s; source already exists at %s", video_id, video_path)
            if progress_callback:
                progress_callback(f"Using existing source video: {video_path.name}", 100.0)
        else:
            logger.info("Downloading %s to %s", url, video_path)
            _download_with_ytdlp(url, video_dir, settings, progress_callback=progress_callback)
            if not video_path.exists():
                raise FileNotFoundError(f"yt-dlp completed but expected output was not found: {video_path}")

        _write_json(metadata_path, metadata)
        if progress_callback:
            progress_callback("Download complete", 100.0)
        return {
            "video_path": str(video_path),
            "metadata_path": str(metadata_path),
            "raw_dir": str(video_dir),
            "metadata": metadata,
            "status": "skipped_existing" if existed_before else "downloaded",
        }
    except (DownloadError, OSError, ValueError) as exc:
        logger.exception("Failed to download YouTube URL: %s", url)
        raise RuntimeError(f"Failed to download YouTube URL: {url}\n\nDetails: {exc}") from exc


def _extract_info(url: str, settings: Settings) -> dict[str, Any]:
    options = _base_ytdlp_options(settings) | {"skip_download": True}
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise ValueError(f"yt-dlp returned unexpected metadata for URL: {url}")
    return info


def _download_with_ytdlp(
    url: str,
    video_dir: Path,
    settings: Settings,
    progress_callback: ProgressCallback | None = None,
) -> None:
    options = _base_ytdlp_options(settings) | {
        "format": settings.ytdlp_format,
        "merge_output_format": "mp4",
        "outtmpl": str((video_dir / "source.%(ext)s").resolve()),
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
    }
    if progress_callback:
        options["progress_hooks"] = [_build_ytdlp_progress_hook(progress_callback)]
    with YoutubeDL(options) as ydl:
        ydl.download([url])


def _build_ytdlp_progress_hook(progress_callback: ProgressCallback) -> Callable[[dict[str, Any]], None]:
    def _hook(status: dict[str, Any]) -> None:
        state = status.get("status")
        filename = Path(str(status.get("filename") or "video")).name
        if state == "downloading":
            percent = _download_percent(status)
            speed = status.get("_speed_str") or ""
            eta = status.get("_eta_str") or ""
            detail = f"{filename}: {percent:.1f}%"
            if speed:
                detail += f" at {speed.strip()}"
            if eta:
                detail += f", ETA {eta.strip()}"
            progress_callback(detail, percent)
        elif state == "finished":
            progress_callback(f"Downloaded {filename}; merging formats if needed", 100.0)

    return _hook


def _download_percent(status: dict[str, Any]) -> float:
    downloaded = status.get("downloaded_bytes") or 0
    total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
    if total:
        return min(100.0, max(0.0, float(downloaded) / float(total) * 100.0))

    percent_text = str(status.get("_percent_str") or "").strip().strip("%")
    try:
        return min(100.0, max(0.0, float(percent_text)))
    except ValueError:
        return 0.0


def _base_ytdlp_options(settings: Settings) -> dict[str, Any]:
    import shutil

    options: dict[str, Any] = {
        "noplaylist": True,
        # Mimic a real browser to reduce bot-detection rejections from YouTube
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
        # Use the android client as a fallback — it bypasses many bot checks
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "socket_timeout": 30,
        "retries": 5,
        "quiet": True,
        "no_warnings": False,
    }
    if settings.ytdlp_cookies_file:
        options["cookiefile"] = settings.ytdlp_cookies_file

    # Provide a JS runtime for YouTube extraction (required since late 2024).
    # js_runtimes must be a dict of {runtime_name: config_dict}.
    # Prefer node if available (installed via packages.txt on Streamlit Cloud),
    # then fall back to deno; omit entirely if neither is found.
    for runtime in ("node", "nodejs", "deno"):
        runtime_path = shutil.which(runtime)
        if runtime_path:
            options["js_runtimes"] = {runtime: {}}
            break

    return options


def _recover_legacy_nested_download(settings: Settings, video_id: str, expected_path: Path) -> None:
    """Move files created by the old doubled data/raw output template into place."""
    nested_path = settings.raw_dir / settings.raw_dir / video_id / "source.mp4"
    if expected_path.exists() or not nested_path.exists():
        return

    expected_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Recovering nested yt-dlp output from %s to %s", nested_path, expected_path)
    nested_path.replace(expected_path)


def _require_video_id(info: dict[str, Any], url: str) -> str:
    video_id = info.get("id")
    if not video_id:
        raise ValueError(f"Could not determine YouTube video id for URL: {url}")
    return str(video_id)


def _build_metadata(info: dict[str, Any], url: str, video_id: str) -> dict[str, Any]:
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "channel": info.get("channel"),
        "duration": info.get("duration"),
        "original_url": url,
        "video_id": video_id,
        "upload_date": info.get("upload_date"),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
