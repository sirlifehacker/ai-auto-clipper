import json
import logging
from pathlib import Path
from typing import Any

from clipper.models import ClipCandidate

logger = logging.getLogger(__name__)

TRANSCRIPT_WEIGHT = 0.60
VISUAL_WEIGHT = 0.40
VISUAL_RISK_PENALTY = 0.75
BAD_VISUAL_RISK_TERMS = (
    "static",
    "low energy",
    "low lighting",
    "bad lighting",
    "poor composition",
    "bad composition",
    "poor vertical",
    "bad for vertical",
    "hard to crop",
    "cluttered",
    "blurry",
    "dark",
)


def rank_candidates_with_video_analysis(
    candidates_path: str,
    visual_analysis_path: str | None,
) -> list[ClipCandidate]:
    """Combine transcript candidate scores with overlapping Gemini visual analysis."""
    candidates_file = Path(candidates_path)
    candidates = _load_candidates(candidates_file)
    visual_moments = _load_visual_moments(visual_analysis_path)

    ranked = [_rank_candidate(candidate, visual_moments) for candidate in candidates]
    ranked.sort(key=lambda candidate: candidate.final_score or candidate.scores.overall_score, reverse=True)

    output_path = candidates_file.parent / "ranked_clip_candidates.json"
    output_path.write_text(
        json.dumps([candidate.model_dump(mode="json") for candidate in ranked], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved %s ranked clip candidate(s) to %s", len(ranked), output_path)
    return ranked


def _load_candidates(candidates_file: Path) -> list[ClipCandidate]:
    if not candidates_file.exists():
        raise FileNotFoundError(f"Clip candidates file not found: {candidates_file}")
    payload = json.loads(candidates_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("clip_candidates.json must contain a list of candidates.")
    return [ClipCandidate.model_validate(item) for item in payload]


def _load_visual_moments(visual_analysis_path: str | None) -> list[dict[str, Any]]:
    if not visual_analysis_path:
        return []

    visual_file = Path(visual_analysis_path)
    if not visual_file.exists():
        logger.warning("Visual analysis file not found; using transcript-only ranking: %s", visual_file)
        return []

    payload = json.loads(visual_file.read_text(encoding="utf-8"))
    moments = payload.get("visual_moments", [])
    if not isinstance(moments, list):
        logger.warning("visual_analysis.json has no valid visual_moments list; using transcript-only ranking.")
        return []
    return [moment for moment in moments if isinstance(moment, dict)]


def _rank_candidate(candidate: ClipCandidate, visual_moments: list[dict[str, Any]]) -> ClipCandidate:
    transcript_score = candidate.scores.overall_score
    matches = _overlapping_visual_moments(candidate, visual_moments)
    if not matches:
        return candidate.model_copy(
            update={
                "visual_score": None,
                "visual_reasoning": "",
                "visual_detected_elements": [],
                "vertical_crop_notes": "",
                "final_score": round(transcript_score, 2),
            }
        )

    weighted_visual_score = _weighted_visual_score(candidate, matches)
    risk_penalty = _risk_penalty(matches)
    adjusted_visual_score = max(0.0, weighted_visual_score - risk_penalty)
    final_score = transcript_score * TRANSCRIPT_WEIGHT + adjusted_visual_score * VISUAL_WEIGHT

    return candidate.model_copy(
        update={
            "visual_score": round(adjusted_visual_score, 2),
            "visual_reasoning": _combine_text_field(matches, "visual_reasoning"),
            "visual_detected_elements": _unique_items(matches, "detected_elements"),
            "vertical_crop_notes": _combine_text_field(matches, "vertical_crop_notes"),
            "final_score": round(final_score, 2),
        }
    )


def _overlapping_visual_moments(
    candidate: ClipCandidate,
    visual_moments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches = []
    for moment in visual_moments:
        overlap = _overlap_seconds(
            candidate.start_time,
            candidate.end_time,
            float(moment.get("start_time", 0)),
            float(moment.get("end_time", 0)),
        )
        if overlap <= 0:
            continue
        candidate_duration = max(0.01, candidate.duration_seconds)
        moment_duration = max(0.01, float(moment.get("end_time", 0)) - float(moment.get("start_time", 0)))
        overlap_ratio = max(overlap / candidate_duration, overlap / moment_duration)
        enriched = dict(moment)
        enriched["_overlap_seconds"] = overlap
        enriched["_overlap_ratio"] = overlap_ratio
        matches.append(enriched)
    return matches


def _weighted_visual_score(candidate: ClipCandidate, matches: list[dict[str, Any]]) -> float:
    weighted_sum = 0.0
    total_weight = 0.0
    for match in matches:
        score = float(match.get("visual_score") or 0)
        weight = float(match.get("_overlap_seconds") or 0)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0

    overlap_coverage = min(
        1.0,
        sum(float(match.get("_overlap_seconds") or 0) for match in matches) / max(0.01, candidate.duration_seconds),
    )
    overlap_boost = 0.85 + (0.15 * overlap_coverage)
    return min(10.0, (weighted_sum / total_weight) * overlap_boost)


def _risk_penalty(matches: list[dict[str, Any]]) -> float:
    penalty = 0.0
    for match in matches:
        risks = [str(risk).lower() for risk in match.get("risks", []) if risk]
        notes = str(match.get("vertical_crop_notes") or "").lower()
        risk_text = " ".join(risks + [notes])
        penalty += sum(1 for term in BAD_VISUAL_RISK_TERMS if term in risk_text) * VISUAL_RISK_PENALTY
    return min(4.0, penalty)


def _overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _combine_text_field(matches: list[dict[str, Any]], field_name: str) -> str:
    parts = []
    for match in matches:
        value = str(match.get(field_name) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return " ".join(parts)


def _unique_items(matches: list[dict[str, Any]], field_name: str) -> list[str]:
    items: list[str] = []
    for match in matches:
        values = match.get(field_name, [])
        if not isinstance(values, list):
            continue
        for value in values:
            item = str(value).strip()
            if item and item not in items:
                items.append(item)
    return items
