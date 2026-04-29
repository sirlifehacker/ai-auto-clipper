import json
import logging
import html
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipper.config import Settings, get_settings
from clipper.models import SourceVideo, TranscriptSegment

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, float | None], None]


class Transcriber:
    """Transcribes source videos into timestamped transcript segments."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, source_video: SourceVideo) -> list[TranscriptSegment]:
        """Run Whisper/faster-whisper and return normalized transcript segments."""
        if source_video.local_path is None:
            raise ValueError("Source video is missing local_path; download it before transcription.")

        output_dir = source_video.local_path.parent
        result = transcribe_video(str(source_video.local_path), str(output_dir), settings=self.settings)
        return [
            TranscriptSegment(
                start_seconds=segment["start"],
                end_seconds=segment["end"],
                text=segment["text"],
            )
            for segment in result["segments"]
        ]


def transcribe_video(
    video_path: str,
    output_dir: str,
    *,
    force: bool = False,
    settings: Settings | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Transcribe a video file and write JSON and text transcript artifacts."""
    settings = settings or get_settings()
    source_path = Path(video_path)
    transcript_dir = Path(output_dir)
    transcript_json_path = transcript_dir / "transcript.json"
    transcript_txt_path = transcript_dir / "transcript.txt"

    if not source_path.exists():
        raise FileNotFoundError(f"Video file not found: {source_path}")

    transcript_dir.mkdir(parents=True, exist_ok=True)

    if transcript_json_path.exists() and transcript_txt_path.exists() and not force:
        logger.info("Skipping transcription; existing transcript found at %s", transcript_json_path)
        if progress_callback:
            progress_callback("Using existing transcript", 100.0)
        return _load_existing_transcript(transcript_json_path, transcript_txt_path)

    logger.info("Transcribing %s with faster-whisper model %s", source_path, settings.whisper_model_size)
    if progress_callback:
        progress_callback(f"Loading faster-whisper model: {settings.whisper_model_size}", None)
    segments, language, duration = _transcribe_with_faster_whisper(source_path, settings, progress_callback)
    if progress_callback:
        progress_callback(f"Transcription complete: {len(segments)} segment(s)", 100.0)

    payload = {
        "source_video_path": str(source_path),
        "detected_language": language,
        "duration": duration,
        "segments": segments,
    }
    transcript_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    transcript_txt_path.write_text(_format_plain_text(segments), encoding="utf-8")

    return {
        "transcript_json_path": str(transcript_json_path),
        "transcript_txt_path": str(transcript_txt_path),
        "segments": segments,
        "detected_language": language,
        "duration": duration,
    }


def transcribe_youtube_captions(
    youtube_url: str,
    output_dir: str,
    *,
    settings: Settings | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any] | None:
    """Use YouTube captions/auto-captions when available and save transcript artifacts."""
    settings = settings or get_settings()
    transcript_dir = Path(output_dir)
    transcript_json_path = transcript_dir / "transcript.json"
    transcript_txt_path = transcript_dir / "transcript.txt"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback("Checking YouTube captions", 5.0)

    caption_url = _select_caption_url(youtube_url, settings)
    if not caption_url:
        if progress_callback:
            progress_callback("No usable YouTube captions found", 100.0)
        return None

    if progress_callback:
        progress_callback("Downloading YouTube captions", 45.0)
    segments = _download_caption_segments(caption_url)
    if not segments:
        if progress_callback:
            progress_callback("YouTube captions were empty", 100.0)
        return None

    payload = {
        "source_video_path": youtube_url,
        "detected_language": "youtube",
        "duration": segments[-1]["end"],
        "segments": segments,
    }
    transcript_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    transcript_txt_path.write_text(_format_plain_text(segments), encoding="utf-8")

    if progress_callback:
        progress_callback(f"Loaded YouTube captions: {len(segments)} segment(s)", 100.0)

    return {
        "transcript_json_path": str(transcript_json_path),
        "transcript_txt_path": str(transcript_txt_path),
        "segments": segments,
        "detected_language": "youtube",
        "duration": payload["duration"],
    }


def _select_caption_url(youtube_url: str, settings: Settings) -> str | None:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required to fetch YouTube captions.") from exc

    options: dict[str, Any] = {"skip_download": True, "quiet": True, "no_warnings": True}
    if settings.ytdlp_cookies_file:
        options["cookiefile"] = settings.ytdlp_cookies_file

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(youtube_url, download=False)

    if not isinstance(info, dict):
        return None

    subtitles = info.get("subtitles") or {}
    automatic_captions = info.get("automatic_captions") or {}
    for captions in (subtitles, automatic_captions):
        caption_url = _caption_url_from_tracks(captions)
        if caption_url:
            return caption_url
    return None


def _caption_url_from_tracks(captions: dict[str, Any]) -> str | None:
    preferred_languages = ("en", "en-US", "en-GB")
    language_keys = list(preferred_languages) + [
        language for language in captions if str(language).startswith("en")
    ]
    for language in language_keys:
        tracks = captions.get(language)
        if not isinstance(tracks, list):
            continue
        for preferred_ext in ("json3", "srv3", "vtt"):
            for track in tracks:
                if isinstance(track, dict) and track.get("ext") == preferred_ext and track.get("url"):
                    return str(track["url"])
    return None


def _download_caption_segments(caption_url: str) -> list[dict[str, Any]]:
    import requests

    response = requests.get(caption_url, timeout=30)
    response.raise_for_status()

    if "json3" in caption_url or response.text.lstrip().startswith("{"):
        return _segments_from_json3(response.json())
    return _segments_from_vtt(response.text)


def _segments_from_json3(payload: dict[str, Any]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or "segs" not in event:
            continue
        text = "".join(str(seg.get("utf8") or "") for seg in event.get("segs", []) if isinstance(seg, dict))
        text = _clean_caption_text(text)
        if not text:
            continue
        start = float(event.get("tStartMs") or 0) / 1000.0
        duration = float(event.get("dDurationMs") or 0) / 1000.0
        segments.append({"start": start, "end": max(start + 0.1, start + duration), "text": text})
    return _merge_caption_segments(segments)


def _segments_from_vtt(vtt_text: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    lines = [line.strip() for line in vtt_text.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        if "-->" not in line:
            index += 1
            continue
        start_text, end_text = [part.strip().split(" ")[0] for part in line.split("-->", 1)]
        index += 1
        text_lines = []
        while index < len(lines) and lines[index]:
            text_lines.append(lines[index])
            index += 1
        text = _clean_caption_text(" ".join(text_lines))
        if text:
            segments.append({"start": _parse_vtt_timestamp(start_text), "end": _parse_vtt_timestamp(end_text), "text": text})
    return _merge_caption_segments(segments)


def _merge_caption_segments(segments: list[dict[str, Any]], target_seconds: float = 8.0) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for segment in segments:
        if current is None:
            current = dict(segment)
            continue
        if float(segment["end"]) - float(current["start"]) <= target_seconds:
            current["end"] = segment["end"]
            current["text"] = f"{current['text']} {segment['text']}".strip()
        else:
            merged.append(current)
            current = dict(segment)
    if current is not None:
        merged.append(current)
    return merged


def _clean_caption_text(text: str) -> str:
    text = html.unescape(text)
    return " ".join(text.replace("\n", " ").split())


def _parse_vtt_timestamp(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2]) if len(parts) >= 2 else 0
    hours = int(parts[-3]) if len(parts) >= 3 else 0
    return hours * 3600 + minutes * 60 + seconds


def _transcribe_with_faster_whisper(
    source_path: Path,
    settings: Settings,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[dict[str, Any]], str, float | None]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install requirements.txt or swap this adapter for OpenAI Whisper."
        ) from exc

    model = WhisperModel(settings.whisper_model_size, device=settings.whisper_device)
    if progress_callback:
        progress_callback("Detecting speech and transcribing audio", 0.0)
    raw_segments, info = model.transcribe(
        str(source_path),
        vad_filter=True,
        word_timestamps=True,
    )

    segments: list[dict[str, Any]] = []
    duration = getattr(info, "duration", None)
    last_progress = -5.0
    for segment in raw_segments:
        item: dict[str, Any] = {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip(),
        }
        words = getattr(segment, "words", None)
        if words:
            item["words"] = [
                {
                    "start": float(word.start),
                    "end": float(word.end),
                    "word": word.word.strip(),
                }
                for word in words
            ]
        segments.append(item)
        if progress_callback:
            progress = _transcription_percent(float(segment.end), duration)
            if progress is None or progress - last_progress >= 2.0 or progress >= 100.0:
                progress_callback(_transcription_detail(float(segment.end), duration, len(segments)), progress)
                last_progress = progress or last_progress

    return segments, getattr(info, "language", "unknown"), duration


def _transcription_percent(segment_end: float, duration: float | None) -> float | None:
    if not duration:
        return None
    return min(100.0, max(0.0, segment_end / float(duration) * 100.0))


def _transcription_detail(segment_end: float, duration: float | None, segment_count: int) -> str:
    if duration:
        return f"Transcribed {_format_minutes(segment_end)} of {_format_minutes(float(duration))} ({segment_count} segments)"
    return f"Transcribed {segment_count} segment(s)"


def _format_minutes(seconds: float) -> str:
    return f"{seconds / 60:.1f} min"


def _load_existing_transcript(transcript_json_path: Path, transcript_txt_path: Path) -> dict[str, Any]:
    payload = json.loads(transcript_json_path.read_text(encoding="utf-8"))
    return {
        "transcript_json_path": str(transcript_json_path),
        "transcript_txt_path": str(transcript_txt_path),
        "segments": payload.get("segments", []),
        "detected_language": payload.get("detected_language"),
        "duration": payload.get("duration"),
    }


def _format_plain_text(segments: list[dict[str, Any]]) -> str:
    return "\n".join(segment["text"] for segment in segments if segment.get("text")).strip() + "\n"
