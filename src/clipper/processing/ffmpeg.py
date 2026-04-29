from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from clipper.models import ClipCandidate, ClipRender, SourceVideo

if TYPE_CHECKING:
    from clipper.config import Settings

logger = logging.getLogger(__name__)
PADDING_SECONDS = 0.25


class VideoProcessor:
    """Trims source videos and renders vertical preview clips with FFmpeg."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def render_vertical_clip(self, source_video: SourceVideo, candidate: ClipCandidate) -> ClipRender:
        """Trim a candidate and crop/scale it to 9:16 vertical format."""
        # TODO: Implement FFmpeg trim, crop/scale, loudness normalization, and preview outputs.
        # TODO: Add smart crop support using face/object tracking once visual analysis exists.
        raise NotImplementedError("FFmpeg clip rendering is not implemented yet.")

    def _output_path_for(self, candidate: ClipCandidate) -> Path:
        safe_title = "".join(char for char in candidate.title if char.isalnum() or char in ("-", "_")).strip()
        filename = f"{candidate.source_video_id}_{int(candidate.start_seconds)}_{safe_title or 'clip'}.mp4"
        return self.settings.clips_dir / filename


def trim_clip(source_video_path: str, candidate: ClipCandidate, output_dir: str) -> str:
    """Trim a horizontal source clip with FFmpeg and store the output path on the candidate."""
    from clipper.config import get_settings

    settings = get_settings()
    source_path = Path(source_video_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source video not found: {source_path}")

    output_path = _build_trim_output_path(candidate, Path(output_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = _probe_duration(source_path, settings)
    start_time, clip_duration = _padded_trim_range(candidate, duration)
    ffmpeg_executable = _resolve_ffmpeg_executable(settings.ffmpeg_path)
    command = [
        ffmpeg_executable,
        "-y",
        "-i",
        str(source_path),
        "-ss",
        _format_timestamp(start_time),
        "-t",
        _format_timestamp(clip_duration),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    logger.info("Trimming clip %s -> %s", candidate.suggested_clip_title or candidate.source_video_id, output_path)
    _run_subprocess(command, "FFmpeg trim failed")
    candidate.local_clip_path = str(output_path)
    return str(output_path)


def crop_to_vertical(input_clip_path: str, output_path: str, resolution: str = "1080x1920") -> str:
    """Convert a horizontal clip to exact 9:16 vertical output using center crop/pad."""
    from clipper.config import get_settings

    settings = get_settings()
    input_path = Path(input_clip_path)
    vertical_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input clip not found: {input_path}")

    width, height = _parse_resolution(resolution)
    vertical_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = _vertical_filter(width, height, settings.ffmpeg_fps)
    ffmpeg_executable = _resolve_ffmpeg_executable(settings.ffmpeg_path)
    command = [
        ffmpeg_executable,
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        settings.ffmpeg_video_codec,
        "-preset",
        settings.ffmpeg_preset,
        "-crf",
        str(settings.ffmpeg_crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        settings.ffmpeg_audio_bitrate,
        "-movflags",
        "+faststart",
        str(vertical_path),
    ]

    logger.info("Cropping vertical clip %s -> %s", input_path, vertical_path)
    _run_subprocess(command, "FFmpeg vertical crop failed")
    return str(vertical_path)


def crop_candidates_to_vertical(
    candidates: list[ClipCandidate],
    resolution: str = "1080x1920",
) -> list[ClipCandidate]:
    """Crop all candidates with local clips to vertical format and update vertical_clip_path."""
    for candidate in candidates:
        if not candidate.local_clip_path:
            logger.warning("Skipping candidate without local_clip_path: %s", candidate.suggested_clip_title)
            continue
        output_path = _vertical_output_path(candidate)
        candidate.vertical_clip_path = crop_to_vertical(candidate.local_clip_path, str(output_path), resolution)
    return candidates


def _vertical_output_path(candidate: ClipCandidate) -> Path:
    clip_id = _clip_id(candidate)
    return Path("data/processed") / candidate.source_video_id / "vertical" / f"{clip_id}_vertical.mp4"


def _parse_resolution(resolution: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", resolution.strip())
    if not match:
        raise ValueError("resolution must be in WIDTHxHEIGHT format, for example 1080x1920.")
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError("resolution width and height must be positive.")
    return width, height


def _vertical_filter(width: int, height: int, fps: int) -> str:
    # Scale to cover the target frame, crop center, then pad as a safety net for narrow inputs.
    return (
        f"[0:v]fps={fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v]"
    )


def _build_trim_output_path(candidate: ClipCandidate, output_dir: Path) -> Path:
    clip_id = _clip_id(candidate)
    return output_dir / f"{clip_id}_raw.mp4"


def _clip_id(candidate: ClipCandidate) -> str:
    title = _slugify(candidate.suggested_clip_title or candidate.title or "clip")
    start = int(round(candidate.start_time * 1000))
    end = int(round(candidate.end_time * 1000))
    return f"{candidate.source_video_id}_{start}_{end}_{title}"[:140].rstrip("_")


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return value or "clip"


def _padded_trim_range(candidate: ClipCandidate, source_duration: float | None) -> tuple[float, float]:
    start = max(0.0, candidate.start_time - PADDING_SECONDS)
    end = candidate.end_time + PADDING_SECONDS
    if source_duration is not None:
        end = min(source_duration, end)
    clip_duration = max(0.1, end - start)
    return start, clip_duration


def _probe_duration(source_path: Path, settings: Settings) -> float | None:
    ffprobe_executable = _resolve_ffprobe_executable(settings.ffprobe_path, settings.ffmpeg_path)
    if ffprobe_executable is None:
        return None
    command = [
        ffprobe_executable,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(source_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("Could not probe source duration; trimming without end clamp: %s", exc)
        return None

    try:
        payload = json.loads(result.stdout)
        return float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.warning("ffprobe returned an unexpected duration payload for %s", source_path)
        return None


def _run_subprocess(command: list[str], error_message: str) -> None:
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg executable was not found. Check FFMPEG_PATH or your system PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"{error_message}: {stderr}") from exc


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


def _resolve_ffprobe_executable(configured_probe: str, configured_ffmpeg: str) -> str | None:
    probe_value = (configured_probe or "").strip()
    if probe_value:
        resolved_probe = shutil.which(probe_value) if probe_value == "ffprobe" else probe_value
        if resolved_probe and (resolved_probe.lower().endswith("ffprobe.exe") or Path(resolved_probe).exists()):
            return resolved_probe

    ffmpeg_path = _resolve_ffmpeg_executable(configured_ffmpeg)
    ffmpeg_path_obj = Path(ffmpeg_path)
    sibling_probe = ffmpeg_path_obj.with_name("ffprobe.exe" if ffmpeg_path_obj.suffix.lower() == ".exe" else "ffprobe")
    if sibling_probe.exists():
        return str(sibling_probe)

    logger.warning("Could not resolve ffprobe executable; trimming without end clamp.")
    return None


def _format_timestamp(seconds: float) -> str:
    return f"{seconds:.3f}"
