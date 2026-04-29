from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    CREATED = "created"
    DOWNLOADED = "downloaded"
    TRANSCRIBED = "transcribed"
    ANALYZED = "analyzed"
    RENDERED = "rendered"
    REVIEW_READY = "review_ready"
    AE_READY = "after_effects_ready"
    UPLOADED = "uploaded"
    LOGGED = "logged"
    FAILED = "failed"


class ClipStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"
    RENDERED = "rendered"
    AFTER_EFFECTS = "after_effects"
    FINAL = "final"
    UPLOADED = "uploaded"


class SourceVideo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    video_id: str | None = None
    title: str | None = None
    uploader: str | None = None
    channel: str | None = None
    duration: float | None = Field(default=None, validation_alias=AliasChoices("duration", "duration_seconds"))
    upload_date: str | None = None
    local_path: Path | None = None

    @property
    def duration_seconds(self) -> float | None:
        return self.duration


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: float = Field(validation_alias=AliasChoices("start", "start_seconds"))
    end: float = Field(validation_alias=AliasChoices("end", "end_seconds"))
    text: str
    words: list[dict] | None = None

    @property
    def start_seconds(self) -> float:
        return self.start

    @property
    def end_seconds(self) -> float:
        return self.end


class ClipScore(BaseModel):
    shock_value: float = 0.0
    emotional_intensity: float = 0.0
    curiosity_gap: float = 0.0
    shareability: float = 0.0
    clarity_without_context: float = 0.0
    hook_strength: float = 0.0
    overall_score: float = 0.0


class ClipCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_video_id: str
    source_url: str = ""
    title: str = ""
    start_time: float = Field(validation_alias=AliasChoices("start_time", "start_seconds"))
    end_time: float = Field(validation_alias=AliasChoices("end_time", "end_seconds"))
    duration: float | None = None
    suggested_clip_title: str = ""
    transcript_excerpt: str
    viral_reasoning: str = Field(default="", validation_alias=AliasChoices("viral_reasoning", "rationale"))
    scores: ClipScore = Field(default_factory=ClipScore)
    status: ClipStatus = ClipStatus.CANDIDATE
    local_clip_path: str | None = None
    vertical_clip_path: str | None = None
    final_clip_path: str | None = None
    google_drive_url: str | None = None
    notion_page_url: str | None = None
    visual_score: float | None = None
    visual_reasoning: str = ""
    visual_detected_elements: list[str] = Field(default_factory=list)
    vertical_crop_notes: str = ""
    final_score: float | None = None
    text_overlay_prompt: str = ""
    vfx_prompt: str = ""
    editor_notes: str = ""
    tags: list[str] = Field(default_factory=list)

    @property
    def start_seconds(self) -> float:
        return self.start_time

    @property
    def end_seconds(self) -> float:
        return self.end_time

    @property
    def duration_seconds(self) -> float:
        return self.duration or self.end_time - self.start_time

    @property
    def rationale(self) -> str:
        return self.viral_reasoning

    @property
    def viral_score(self) -> float:
        return self.scores.overall_score


class ClipRender(BaseModel):
    candidate: ClipCandidate
    local_path: Path
    preview_path: Path | None = None
    approved: bool = False
    drive_file_id: str | None = None
    notion_page_id: str | None = None


class ProcessingJob(BaseModel):
    urls: list[str]
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.CREATED
    source_videos: list[SourceVideo] = Field(default_factory=list)
    transcript_segments: dict[str, list[TranscriptSegment]] = Field(default_factory=dict)
    candidates: list[ClipCandidate] = Field(default_factory=list)
    renders: list[ClipRender] = Field(default_factory=list)
    error: str | None = None


Job = ProcessingJob
