from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING
from typing import Any

from pydantic import ValidationError

from clipper.models import ClipCandidate, ClipScore

if TYPE_CHECKING:
    from clipper.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are an elite short-form content strategist. Your job is to find moments from long-form videos "
    "that can become viral social shorts. You are looking for clips with strong hooks, emotional intensity, "
    "controversy, intrigue, practical value, or high shareability. You must only select clips that make sense "
    "as standalone 35-60 second videos."
)


class GeminiAnalyzer:
    """Gemini / Vertex AI analyzer for transcript-based viral moment scoring."""

    def __init__(self, settings: Settings | None = None, batch_size: int = 10) -> None:
        if settings is None:
            from clipper.config import get_settings

            settings = get_settings()
        self.settings = settings
        self.batch_size = batch_size

    def analyze_windows(self, windows: list[dict[str, Any]], metadata: dict[str, Any]) -> list[ClipCandidate]:
        candidates: list[ClipCandidate] = []
        for batch in chunked(windows, self.batch_size):
            prompt = build_gemini_prompt(batch, metadata)
            raw_response = self._generate_with_retries(prompt)
            candidates.extend(parse_clip_candidates(raw_response, metadata, batch))
        return candidates

    def _generate_with_retries(self, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.gemini_max_retries + 1):
            try:
                return self._generate_content(prompt)
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini analysis attempt %s failed: %s", attempt, exc)
                if attempt < self.settings.gemini_max_retries:
                    time.sleep(self.settings.gemini_retry_delay_seconds * attempt)
        raise RuntimeError("Gemini analysis failed after retries.") from last_error

    def _generate_content(self, prompt: str) -> str:
        if self.settings.gemini_use_vertex or (not self.settings.gemini_api_key and self.settings.google_cloud_project):
            return generate_with_vertex(prompt, self.settings)
        return generate_with_gemini_api(prompt, self.settings)


def build_gemini_prompt(windows: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    """Build the JSON-only prompt sent to Gemini."""
    normalized_windows = [
        {
            "window_id": index,
            "start": window["start"],
            "end": window["end"],
            "duration": round(window["end"] - window["start"], 2),
            "hook_text": window.get("hook_text", ""),
            "transcript_excerpt": window.get("text", ""),
        }
        for index, window in enumerate(windows)
    ]
    payload = {
        "source_video": {
            "video_id": metadata.get("video_id"),
            "source_url": metadata.get("original_url"),
            "title": metadata.get("title"),
            "duration": metadata.get("duration"),
            "channel": metadata.get("channel") or metadata.get("uploader"),
        },
        "candidate_windows": normalized_windows,
    }
    return f"""
{SYSTEM_INSTRUCTION}

Return valid JSON only. Do not include markdown, prose, comments, code fences, or explanations outside JSON.

Analyze each candidate window and return only the windows that are strong standalone short-form clips.
Every selected clip must be between 35 and 60 seconds and must contain a clear hook in the first 3-5 seconds.

Score each selected clip from 0 to 10 on:
- shock_value
- emotional_intensity
- curiosity_gap
- shareability
- clarity_without_context
- hook_strength
- overall_score

Return this exact JSON shape:
{{
  "candidates": [
    {{
      "window_id": 0,
      "source_video_id": "string",
      "source_url": "string",
      "title": "string",
      "start_time": 0.0,
      "end_time": 0.0,
      "duration": 45.0,
      "suggested_clip_title": "string",
      "transcript_excerpt": "string",
      "viral_reasoning": "string",
      "scores": {{
        "shock_value": 0.0,
        "emotional_intensity": 0.0,
        "curiosity_gap": 0.0,
        "shareability": 0.0,
        "clarity_without_context": 0.0,
        "hook_strength": 0.0,
        "overall_score": 0.0
      }},
      "status": "candidate",
      "local_clip_path": null,
      "vertical_clip_path": null,
      "final_clip_path": null,
      "google_drive_url": null,
      "notion_page_url": null
    }}
  ]
}}

Input:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def generate_with_gemini_api(prompt: str, settings: Settings) -> str:
    """Call the Gemini Developer API using GEMINI_API_KEY."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required when GEMINI_USE_VERTEX is false.")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai is not installed. Run pip install -r requirements.txt.") from exc

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )
    return response.text


def generate_with_vertex(prompt: str, settings: Settings) -> str:
    """Call Gemini through Vertex AI using Google application credentials."""
    if not settings.google_cloud_project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required for Vertex AI Gemini analysis.")

    try:
        import vertexai
        from vertexai.generative_models import GenerationConfig, GenerativeModel
    except ImportError as exc:
        raise RuntimeError("google-cloud-aiplatform is not installed. Run pip install -r requirements.txt.") from exc

    from ai.video_analyzer import configure_google_application_credentials

    configure_google_application_credentials(settings)
    vertexai.init(project=settings.google_cloud_project, location=settings.google_cloud_location)
    model = GenerativeModel(settings.vertex_model)
    response = model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return response.text


def parse_clip_candidates(
    raw_response: str,
    metadata: dict[str, Any],
    windows: list[dict[str, Any]],
) -> list[ClipCandidate]:
    """Parse Gemini JSON and validate each candidate against the ClipCandidate schema."""
    payload = extract_json_payload(raw_response)
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("Gemini response must contain a candidates list.")

    candidates: list[ClipCandidate] = []
    for raw_candidate in raw_candidates:
        normalized = normalize_candidate_payload(raw_candidate, metadata, windows)
        try:
            candidates.append(ClipCandidate.model_validate(normalized))
        except ValidationError as exc:
            raise ValueError(f"Gemini returned invalid ClipCandidate JSON: {exc}") from exc
    return candidates


def extract_json_payload(raw_response: str) -> dict[str, Any]:
    """Extract and parse a JSON object from a Gemini response."""
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
        raise ValueError("Gemini response JSON must be an object.")
    return parsed


def normalize_candidate_payload(
    raw_candidate: dict[str, Any],
    metadata: dict[str, Any],
    windows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fill provider omissions and normalize fields before Pydantic validation."""
    if not isinstance(raw_candidate, dict):
        raise ValueError("Each Gemini candidate must be a JSON object.")

    window = _window_for_candidate(raw_candidate, windows)
    start = float(raw_candidate.get("start_time", window.get("start", 0.0)))
    end = float(raw_candidate.get("end_time", window.get("end", start)))
    duration = float(raw_candidate.get("duration", round(end - start, 2)))
    scores = raw_candidate.get("scores") or {}

    return {
        "source_video_id": raw_candidate.get("source_video_id") or metadata.get("video_id") or "",
        "source_url": raw_candidate.get("source_url") or metadata.get("original_url") or "",
        "title": raw_candidate.get("title") or metadata.get("title") or "Untitled source video",
        "start_time": start,
        "end_time": end,
        "duration": duration,
        "suggested_clip_title": raw_candidate.get("suggested_clip_title") or "Untitled clip",
        "transcript_excerpt": raw_candidate.get("transcript_excerpt") or window.get("text") or "",
        "viral_reasoning": raw_candidate.get("viral_reasoning") or "",
        "scores": normalize_scores(scores),
        "status": raw_candidate.get("status") or "candidate",
        "local_clip_path": raw_candidate.get("local_clip_path"),
        "vertical_clip_path": raw_candidate.get("vertical_clip_path"),
        "final_clip_path": raw_candidate.get("final_clip_path"),
        "google_drive_url": raw_candidate.get("google_drive_url"),
        "notion_page_url": raw_candidate.get("notion_page_url"),
        "tags": raw_candidate.get("tags") or [],
    }


def normalize_scores(scores: dict[str, Any]) -> dict[str, float]:
    """Clamp score fields to the 0-10 range expected by ClipScore."""
    validated = {}
    for field in ClipScore.model_fields:
        value = scores.get(field, 0.0)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        validated[field] = max(0.0, min(10.0, numeric))
    return validated


def chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    """Yield fixed-size batches for provider requests."""
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _window_for_candidate(raw_candidate: dict[str, Any], windows: list[dict[str, Any]]) -> dict[str, Any]:
    window_id = raw_candidate.get("window_id")
    if isinstance(window_id, int) and 0 <= window_id < len(windows):
        return windows[window_id]

    start = raw_candidate.get("start_time")
    if start is not None:
        for window in windows:
            if abs(float(window["start"]) - float(start)) < 0.5:
                return window

    return windows[0] if windows else {}
