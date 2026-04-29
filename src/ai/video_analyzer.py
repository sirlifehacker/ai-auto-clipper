from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from clipper.config import Settings

logger = logging.getLogger(__name__)

VIDEO_ANALYSIS_INSTRUCTION = """
You are an elite short-form video strategist and visual analyst.
Analyze this long-form video directly using multimodal video understanding.
Find visually compelling moments that can improve short-form clip selection.
Prioritize moments with expressive faces, dramatic gestures, visible emotion,
scene changes, on-screen text, strong visual context, and high social short potential.
Also identify visual problems like static framing, low energy, bad lighting, poor composition,
or anything that would make a short less engaging.

Return valid JSON only. Do not include markdown, prose, comments, or code fences.
""".strip()


class VisualMoment(BaseModel):
    start_time: float
    end_time: float
    visual_score: float = Field(ge=0.0, le=10.0)
    visual_reasoning: str
    detected_elements: list[str] = Field(default_factory=list)
    vertical_crop_notes: str = ""
    risks: list[str] = Field(default_factory=list)


class VisualAnalysis(BaseModel):
    source_video_id: str
    visual_moments: list[VisualMoment] = Field(default_factory=list)
    overall_visual_summary: str = ""
    recommended_visual_style: str = ""


class MockVideoAnalyzer:
    """Local no-credential visual analyzer for tests and offline development."""

    def analyze(
        self,
        video_path: Path,
        metadata: dict[str, Any],
        transcript: dict[str, Any] | None = None,
        fallback_reason: str | None = None,
    ) -> VisualAnalysis:
        duration = float(metadata.get("duration") or _duration_from_transcript(transcript) or 60)
        moments = _mock_moments_from_transcript(transcript, duration)
        summary = "Mock visual analysis generated locally without calling Vertex AI."
        if fallback_reason:
            summary = f"{summary} Fallback reason: {fallback_reason}"

        return VisualAnalysis(
            source_video_id=str(metadata.get("video_id") or video_path.parent.name),
            visual_moments=moments,
            overall_visual_summary=summary,
            recommended_visual_style=(
                "Use centered 9:16 crop, large captions, and punch-in cuts around high-energy transcript moments."
            ),
        )


class VertexGeminiVideoAnalyzer:
    """Direct video analyzer using Gemini Flash on Vertex AI."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def analyze(
        self,
        video_path: Path,
        metadata: dict[str, Any],
        transcript: dict[str, Any] | None = None,
    ) -> VisualAnalysis:
        prompt = build_video_analysis_prompt(metadata, transcript)
        video_part = self._build_video_part(video_path)
        raw_response = self._generate_with_retries(prompt, video_part)
        return parse_visual_analysis(raw_response, metadata, video_path)

    def _build_video_part(self, video_path: Path) -> Any:
        from vertexai.generative_models import Part

        max_direct_bytes = self.settings.video_direct_upload_max_mb * 1024 * 1024
        file_size = video_path.stat().st_size
        mime_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"

        if file_size <= max_direct_bytes:
            logger.info("Using direct Vertex video file input for %s", video_path)
            return Part.from_data(video_path.read_bytes(), mime_type=mime_type)

        if not self.settings.gcs_temp_bucket:
            proxy_path = build_video_analysis_proxy(video_path, self.settings)
            if proxy_path.stat().st_size <= max_direct_bytes:
                logger.info("Using compressed visual analysis proxy for Vertex input: %s", proxy_path)
                return Part.from_data(proxy_path.read_bytes(), mime_type="video/mp4")
            raise VideoTooLargeError(
                f"{video_path} is {file_size} bytes, and proxy {proxy_path} is still above "
                "VIDEO_DIRECT_UPLOAD_MAX_MB. Set GCS_TEMP_BUCKET or increase VIDEO_DIRECT_UPLOAD_MAX_MB."
            )

        gcs_uri = upload_video_to_gcs(video_path, self.settings.gcs_temp_bucket)
        logger.info("Using GCS video input for Vertex analysis: %s", gcs_uri)
        return Part.from_uri(gcs_uri, mime_type=mime_type)

    def _generate_with_retries(self, prompt: str, video_part: Any) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.video_analysis_max_retries + 1):
            try:
                return generate_vertex_video_response(prompt, video_part, self.settings)
            except Exception as exc:
                last_error = exc
                logger.warning("Vertex video analysis attempt %s failed: %s", attempt, exc)
                if attempt < self.settings.video_analysis_max_retries:
                    time.sleep(self.settings.video_analysis_retry_delay_seconds * attempt)
        raise RuntimeError("Vertex video analysis failed after retries.") from last_error


class VideoTooLargeError(RuntimeError):
    """Raised when a video is too large for direct upload and no GCS bucket is configured."""


def analyze_video_with_gemini(
    video_path: str,
    metadata_path: str,
    transcript_path: str | None = None,
) -> dict[str, Any]:
    """Analyze a local video and save visual_analysis.json."""
    from clipper.config import get_settings

    settings = get_settings()
    source_path = Path(video_path)
    metadata_file = Path(metadata_path)
    transcript_file = Path(transcript_path) if transcript_path else None

    if not source_path.exists():
        raise FileNotFoundError(f"Video file not found: {source_path}")
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_file}")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    transcript = _load_optional_json(transcript_file)
    output_path = metadata_file.parent / "visual_analysis.json"

    analyzer = _build_video_analyzer(settings)
    analysis = analyzer.analyze(source_path, metadata, transcript)

    payload = analysis.model_dump(mode="json")
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def build_video_analysis_prompt(metadata: dict[str, Any], transcript: dict[str, Any] | None = None) -> str:
    """Build a structured JSON-only prompt for direct video analysis."""
    transcript_context = _compact_transcript_context(transcript)
    prompt_payload = {
        "source_video": {
            "video_id": metadata.get("video_id"),
            "title": metadata.get("title"),
            "source_url": metadata.get("original_url"),
            "duration": metadata.get("duration"),
            "channel": metadata.get("channel") or metadata.get("uploader"),
        },
        "transcript_context": transcript_context,
    }
    return f"""
{VIDEO_ANALYSIS_INSTRUCTION}

Expected JSON shape:
{{
  "source_video_id": "string",
  "visual_moments": [
    {{
      "start_time": 123.5,
      "end_time": 178.2,
      "visual_score": 8.7,
      "visual_reasoning": "why this moment is visually compelling for short-form",
      "detected_elements": [
        "expressive face",
        "dramatic gesture",
        "scene change",
        "on-screen text"
      ],
      "vertical_crop_notes": "how to crop or frame this moment for 9:16",
      "risks": [
        "static shot",
        "low lighting"
      ]
    }}
  ],
  "overall_visual_summary": "summary of visual strengths and weaknesses",
  "recommended_visual_style": "editing and crop style recommendation"
}}

Find useful timestamp ranges for clip selection. Prefer ranges that overlap with strong visual emotion,
gestures, scene changes, on-screen text, or high-energy delivery. Include visual problems when present.

Input metadata:
{json.dumps(prompt_payload, ensure_ascii=False)}
""".strip()


def generate_vertex_video_response(prompt: str, video_part: Any, settings: Settings) -> str:
    """Call Gemini Flash through Vertex AI with a direct video part."""
    if not settings.google_cloud_project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required for Vertex AI video analysis.")

    try:
        import vertexai
        from vertexai.generative_models import GenerationConfig, GenerativeModel
    except ImportError as exc:
        raise RuntimeError("google-cloud-aiplatform is not installed. Run pip install -r requirements.txt.") from exc

    configure_google_application_credentials(settings)
    vertexai.init(project=settings.google_cloud_project, location=settings.google_cloud_location)
    model = GenerativeModel(settings.vertex_video_model)
    response = model.generate_content(
        [prompt, video_part],
        generation_config=GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return response.text


def upload_video_to_gcs(video_path: Path, bucket_name: str) -> str:
    """Upload a local video to GCS and return a gs:// URI for Vertex video input."""
    from clipper.config import get_settings

    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError("google-cloud-storage is not installed. Run pip install -r requirements.txt.") from exc

    configure_google_application_credentials(get_settings())
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob_name = f"ai-auto-clipper/tmp/{video_path.stem}-{uuid4().hex}{video_path.suffix}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(video_path))
    return f"gs://{bucket_name}/{blob_name}"


def build_video_analysis_proxy(video_path: Path, settings: Settings) -> Path:
    """Create a small whole-video proxy for visual-only Gemini inspection."""
    proxy_path = video_path.parent / "visual_analysis_proxy.mp4"
    if proxy_path.exists():
        return proxy_path

    ffmpeg_executable = _resolve_ffmpeg_executable(settings.ffmpeg_path)
    command = [
        ffmpeg_executable,
        "-y",
        "-i",
        str(video_path),
        "-an",
        "-vf",
        "fps=1/5,scale=320:-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "35",
        "-movflags",
        "+faststart",
        str(proxy_path),
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg executable was not found. Check FFMPEG_PATH or your system PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"Failed to create visual analysis proxy: {stderr}") from exc

    return proxy_path


def configure_google_application_credentials(settings: Settings) -> None:
    """Expose .env credential path to Google SDK clients."""
    if settings.google_application_credentials:
        configured = Path(settings.google_application_credentials).expanduser()
        if not configured.is_absolute():
            configured = (Path.cwd() / configured).resolve()
        if configured.exists():
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(configured))
            return
        logger.warning("Configured GOOGLE_APPLICATION_CREDENTIALS does not exist: %s", configured)

    local_default = Path.cwd() / "google-service-account.json"
    if local_default.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(local_default.resolve()))


def _resolve_ffmpeg_executable(configured_path: str) -> str:
    configured = (configured_path or "").strip()
    if configured:
        resolved = shutil.which(configured) if configured == "ffmpeg" else configured
        if resolved and Path(resolved).exists():
            return resolved
        if resolved and resolved.lower().endswith("ffmpeg.exe"):
            return resolved

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(
            "FFmpeg executable was not found. Install FFmpeg on PATH, set FFMPEG_PATH, "
            "or install imageio-ffmpeg (pip install imageio-ffmpeg)."
        ) from exc


def parse_visual_analysis(raw_response: str, metadata: dict[str, Any], video_path: Path) -> VisualAnalysis:
    """Parse and validate Vertex/Gemini JSON into a VisualAnalysis model."""
    payload = extract_json_payload(raw_response)
    payload.setdefault("source_video_id", metadata.get("video_id") or video_path.parent.name)
    payload.setdefault("visual_moments", [])
    payload.setdefault("overall_visual_summary", "")
    payload.setdefault("recommended_visual_style", "")
    try:
        return VisualAnalysis.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Gemini returned invalid visual analysis JSON: {exc}") from exc


def extract_json_payload(raw_response: str) -> dict[str, Any]:
    """Extract JSON object from a model response."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("Video analysis response JSON must be an object.")
    return parsed


def _build_video_analyzer(settings: Settings) -> MockVideoAnalyzer | VertexGeminiVideoAnalyzer:
    provider = settings.video_analyzer_provider.lower().strip()
    if provider == "mock":
        return MockVideoAnalyzer()
    if provider in {"vertex", "gemini", "gemini_flash"}:
        return VertexGeminiVideoAnalyzer(settings)
    raise ValueError(f"Unsupported VIDEO_ANALYZER_PROVIDER: {settings.video_analyzer_provider}")


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_transcript_context(transcript: dict[str, Any] | None, max_segments: int = 60) -> list[dict[str, Any]]:
    if not transcript:
        return []
    segments = transcript.get("segments", [])
    if not isinstance(segments, list):
        return []

    if len(segments) <= max_segments:
        selected = segments
    else:
        step = max(1, len(segments) // max_segments)
        selected = segments[::step][:max_segments]

    return [
        {
            "start": segment.get("start"),
            "end": segment.get("end"),
            "text": segment.get("text", ""),
        }
        for segment in selected
        if isinstance(segment, dict)
    ]


def _duration_from_transcript(transcript: dict[str, Any] | None) -> float | None:
    if not transcript:
        return None
    duration = transcript.get("duration")
    if duration:
        return float(duration)
    segments = transcript.get("segments", [])
    if isinstance(segments, list) and segments:
        last = segments[-1]
        if isinstance(last, dict) and last.get("end") is not None:
            return float(last["end"])
    return None


def _mock_moments_from_transcript(transcript: dict[str, Any] | None, duration: float) -> list[VisualMoment]:
    if not transcript or not isinstance(transcript.get("segments"), list):
        return [
            VisualMoment(
                start_time=0,
                end_time=min(45, duration),
                visual_score=5.0,
                visual_reasoning="Mock fallback moment. Real visual signals require Vertex AI video analysis.",
                detected_elements=["unknown visual content"],
                vertical_crop_notes="Use center crop until face/object tracking is available.",
                risks=["mock analysis", "visual content not inspected"],
            )
        ]

    scored_segments = [
        segment
        for segment in transcript["segments"]
        if isinstance(segment, dict) and _contains_high_energy_text(str(segment.get("text", "")))
    ]
    selected = scored_segments[:5] or transcript["segments"][:3]
    moments: list[VisualMoment] = []
    for segment in selected:
        start = float(segment.get("start") or 0)
        end = min(duration, max(start + 35, float(segment.get("end") or start + 45)))
        moments.append(
            VisualMoment(
                start_time=round(start, 2),
                end_time=round(min(end, start + 60), 2),
                visual_score=5.5,
                visual_reasoning="Mock visual moment inferred from transcript energy, not direct video understanding.",
                detected_elements=["transcript-selected moment"],
                vertical_crop_notes="Review manually for face position before rendering vertical crop.",
                risks=["mock analysis", "no direct visual inspection"],
            )
        )
    return moments


def _contains_high_energy_text(text: str) -> bool:
    lower = text.lower()
    return any(
        keyword in lower
        for keyword in (
            "shocking",
            "crazy",
            "unbelievable",
            "angry",
            "excited",
            "look",
            "listen",
            "watch",
            "this is why",
            "you need to",
        )
    )
