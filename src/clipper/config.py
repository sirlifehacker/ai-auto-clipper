from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    local_state_backend: str = "sqlite"
    database_url: str = "sqlite:///data/jobs/clipper.sqlite3"

    downloads_dir: Path = Path("data/downloads")
    raw_dir: Path = Path("data/raw")
    input_dir: Path = Path("data/input")
    transcripts_dir: Path = Path("data/transcripts")
    clips_dir: Path = Path("data/clips")
    processed_dir: Path = Path("data/processed")

    ytdlp_cookies_file: str | None = None
    ytdlp_format: str = "bv*[height<=720]+ba/best[height<=720]/best"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ffmpeg_video_codec: str = "libx264"
    ffmpeg_preset: str = "slow"
    ffmpeg_crf: int = 18
    ffmpeg_audio_bitrate: str = "192k"
    ffmpeg_fps: int = 30

    whisper_model_size: str = "base"
    whisper_device: str = "auto"
    transcription_provider: str = "youtube_or_whisper"

    ai_provider: str = "gemini"
    analyzer_provider: str = "mock"
    video_analyzer_provider: str = "mock"
    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_model: str = "gemini-1.5-pro"
    gemini_max_retries: int = 3
    gemini_retry_delay_seconds: float = 2.0
    gemini_use_vertex: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    vertex_model: str = "gemini-1.5-pro"
    vertex_video_model: str = "gemini-1.5-flash"
    gcs_temp_bucket: str | None = None
    video_direct_upload_max_mb: int = 20
    video_analysis_max_retries: int = 3
    video_analysis_retry_delay_seconds: float = 2.0

    google_drive_folder_id: str | None = None
    google_application_credentials: str | None = None
    google_oauth_client_secret_file: str | None = None

    notion_api_key: str | None = Field(default=None, repr=False)
    notion_database_id: str | None = None

    after_effects_mcp_server_url: str | None = None

    def ensure_local_dirs(self) -> None:
        """Create local working directories if they do not exist."""
        for path in (
            self.downloads_dir,
            self.raw_dir,
            self.input_dir,
            self.transcripts_dir,
            self.clips_dir,
            self.processed_dir,
            Path("data/jobs"),
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
