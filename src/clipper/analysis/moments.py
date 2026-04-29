from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai.gemini_analyzer import GeminiAnalyzer
from clipper.models import ClipCandidate, ClipScore, TranscriptSegment

if TYPE_CHECKING:
    from clipper.config import Settings

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, float | None], None]

MIN_CLIP_SECONDS = 35.0
MAX_CLIP_SECONDS = 60.0
DEFAULT_WINDOW_SECONDS = 45.0
WINDOW_STEP_SECONDS = 12.0


class ViralMomentAnalyzer(ABC):
    """Provider abstraction for scoring candidate transcript windows."""

    @abstractmethod
    def analyze_windows(self, windows: list[dict[str, Any]], metadata: dict[str, Any]) -> list[ClipCandidate]:
        """Score transcript windows and return clip candidates."""


class MockViralMomentAnalyzer(ViralMomentAnalyzer):
    """Heuristic transcript scorer used until Gemini or Vertex AI is wired in."""

    keyword_groups = {
        "shock_value": [
            "shocking",
            "crazy",
            "insane",
            "unbelievable",
            "secret",
            "exposed",
            "scam",
            "lie",
            "mistake",
            "dangerous",
        ],
        "emotional_intensity": [
            "love",
            "hate",
            "afraid",
            "fear",
            "angry",
            "devastated",
            "heartbreaking",
            "excited",
            "pain",
            "changed my life",
        ],
        "curiosity_gap": [
            "why",
            "how",
            "what happened",
            "nobody",
            "most people",
            "you won't believe",
            "the reason",
            "turns out",
            "I realized",
        ],
        "shareability": [
            "you need to",
            "stop",
            "start",
            "save this",
            "remember",
            "framework",
            "step",
            "strategy",
            "tactic",
            "do this",
        ],
        "hook_strength": [
            "here's",
            "listen",
            "look",
            "the truth",
            "the problem",
            "the biggest",
            "first",
            "never",
            "always",
        ],
    }

    def analyze_windows(self, windows: list[dict[str, Any]], metadata: dict[str, Any]) -> list[ClipCandidate]:
        candidates: list[ClipCandidate] = []
        for window in windows:
            text = window["text"]
            hook_text = window["hook_text"]
            scores = self._score_text(text, hook_text)
            if scores.overall_score <= 0:
                continue

            candidates.append(
                ClipCandidate(
                    source_video_id=str(metadata.get("video_id", "")),
                    source_url=str(metadata.get("original_url", "")),
                    title=str(metadata.get("title") or "Untitled source video"),
                    start_time=window["start"],
                    end_time=window["end"],
                    duration=round(window["end"] - window["start"], 2),
                    suggested_clip_title=self._suggest_title(text, metadata),
                    transcript_excerpt=text,
                    viral_reasoning=self._reasoning(scores, text),
                    scores=scores,
                    tags=self._tags_for(scores),
                )
            )
        return candidates

    def _score_text(self, text: str, hook_text: str) -> ClipScore:
        lower_text = text.lower()
        lower_hook = hook_text.lower()
        group_scores = {
            group: self._keyword_score(lower_text, keywords)
            for group, keywords in self.keyword_groups.items()
        }
        group_scores["hook_strength"] = min(
            10.0,
            group_scores["hook_strength"] + self._keyword_score(lower_hook, self.keyword_groups["hook_strength"]) * 0.8,
        )
        clarity = self._clarity_score(lower_text)
        overall = (
            group_scores["shock_value"] * 0.17
            + group_scores["emotional_intensity"] * 0.15
            + group_scores["curiosity_gap"] * 0.18
            + group_scores["shareability"] * 0.17
            + clarity * 0.13
            + group_scores["hook_strength"] * 0.20
        )
        return ClipScore(
            shock_value=round(group_scores["shock_value"], 2),
            emotional_intensity=round(group_scores["emotional_intensity"], 2),
            curiosity_gap=round(group_scores["curiosity_gap"], 2),
            shareability=round(group_scores["shareability"], 2),
            clarity_without_context=round(clarity, 2),
            hook_strength=round(group_scores["hook_strength"], 2),
            overall_score=round(min(10.0, overall), 2),
        )

    def _keyword_score(self, text: str, keywords: list[str]) -> float:
        hits = sum(text.count(keyword) for keyword in keywords)
        question_bonus = 1 if "?" in text else 0
        return min(10.0, hits * 1.6 + question_bonus)

    def _clarity_score(self, text: str) -> float:
        context_penalties = sum(text.count(term) for term in ["as I said", "earlier", "that thing", "this guy", "they did"])
        sentence_count = max(1, len(re.findall(r"[.!?]", text)))
        word_count = len(text.split())
        density = min(10.0, sentence_count * 1.2 + word_count / 45)
        return max(0.0, density - context_penalties * 1.5)

    def _suggest_title(self, text: str, metadata: dict[str, Any]) -> str:
        first_sentence = re.split(r"[.!?]", text.strip())[0]
        if 8 <= len(first_sentence.split()) <= 14:
            return first_sentence[:90]
        title = str(metadata.get("title") or "Viral clip")
        return f"Best moment from {title}"[:90]

    def _reasoning(self, scores: ClipScore, text: str) -> str:
        strongest = max(
            [
                ("shock value", scores.shock_value),
                ("emotion", scores.emotional_intensity),
                ("curiosity gap", scores.curiosity_gap),
                ("shareability", scores.shareability),
                ("hook", scores.hook_strength),
            ],
            key=lambda item: item[1],
        )
        return (
            f"Scores strongest on {strongest[0]} and opens with a usable hook. "
            f"The excerpt is self-contained enough for short-form context: {text[:140].strip()}"
        )

    def _tags_for(self, scores: ClipScore) -> list[str]:
        tags = []
        if scores.shock_value >= 3:
            tags.append("shocking")
        if scores.emotional_intensity >= 3:
            tags.append("emotional")
        if scores.curiosity_gap >= 3:
            tags.append("curiosity")
        if scores.shareability >= 3:
            tags.append("practical")
        return tags


def find_clip_candidates(
    transcript_path: str,
    metadata_path: str,
    max_candidates: int = 10,
    analyzer: ViralMomentAnalyzer | None = None,
    provider: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[ClipCandidate]:
    """Find transcript-only viral clip candidates and save clip_candidates.json."""
    transcript_file = Path(transcript_path)
    metadata_file = Path(metadata_path)
    transcript = json.loads(transcript_file.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    from clipper.config import get_settings

    settings = get_settings()
    analyzer = analyzer or _build_analyzer(settings, provider)

    segments = _load_segments(transcript)
    windows = _build_sliding_windows(segments)
    logger.info("Scoring %s candidate transcript windows", len(windows))
    if progress_callback:
        progress_callback(f"Built {len(windows)} transcript windows from {len(segments)} segment(s)", 25.0)

    if progress_callback:
        progress_callback("Scoring candidate windows", 50.0)
    candidates = _analyze_with_fallback(analyzer, windows, metadata)
    candidates = [
        candidate
        for candidate in candidates
        if MIN_CLIP_SECONDS <= candidate.duration_seconds <= MAX_CLIP_SECONDS
    ]
    candidates.sort(key=lambda candidate: candidate.scores.overall_score, reverse=True)
    candidates = candidates[:max_candidates]
    if progress_callback:
        progress_callback(f"Selected {len(candidates)} clip(s)", 90.0)

    output_path = metadata_file.parent / "clip_candidates.json"
    output_path.write_text(
        json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %s clip candidate(s) to %s", len(candidates), output_path)
    if progress_callback:
        progress_callback("Candidate search complete", 100.0)
    return candidates


def _build_analyzer(settings: Settings, provider: str | None = None) -> ViralMomentAnalyzer:
    selected_provider = (provider or settings.analyzer_provider).lower().strip()
    if selected_provider == "gemini":
        return GeminiAnalyzer(settings=settings)
    if selected_provider == "mock":
        return MockViralMomentAnalyzer()
    raise ValueError(f"Unsupported analyzer provider: {selected_provider}. Use 'mock' or 'gemini'.")


def _analyze_with_fallback(
    analyzer: ViralMomentAnalyzer,
    windows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[ClipCandidate]:
    try:
        return analyzer.analyze_windows(windows, metadata)
    except Exception as exc:
        if isinstance(analyzer, MockViralMomentAnalyzer):
            raise
        logger.exception("Configured analyzer failed; falling back to mock analyzer: %s", exc)
        return MockViralMomentAnalyzer().analyze_windows(windows, metadata)


def _load_segments(transcript: dict[str, Any]) -> list[TranscriptSegment]:
    return [TranscriptSegment.model_validate(segment) for segment in transcript.get("segments", [])]


def _build_sliding_windows(segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    if not segments:
        return windows

    next_start_at = segments[0].start
    for start_index, start_segment in enumerate(segments):
        if start_segment.start < next_start_at:
            continue

        window_segments: list[TranscriptSegment] = []
        for segment in segments[start_index:]:
            if segment.end - start_segment.start > MAX_CLIP_SECONDS:
                break
            window_segments.append(segment)

        valid_segments = [
            segment
            for segment in window_segments
            if MIN_CLIP_SECONDS <= segment.end - start_segment.start <= MAX_CLIP_SECONDS
        ]
        if not valid_segments:
            continue

        end_segment = min(valid_segments, key=lambda segment: abs((segment.end - start_segment.start) - DEFAULT_WINDOW_SECONDS))
        selected = [segment for segment in window_segments if segment.end <= end_segment.end]
        text = " ".join(segment.text.strip() for segment in selected if segment.text.strip())
        hook_text = " ".join(
            segment.text.strip()
            for segment in selected
            if segment.start < start_segment.start + 5
        )
        windows.append(
            {
                "start": round(start_segment.start, 2),
                "end": round(end_segment.end, 2),
                "text": text,
                "hook_text": hook_text,
            }
        )
        next_start_at = start_segment.start + WINDOW_STEP_SECONDS

    return windows
