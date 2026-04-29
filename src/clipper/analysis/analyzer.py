from clipper.config import Settings
from clipper.analysis.moments import MockViralMomentAnalyzer
from clipper.models import ClipCandidate, SourceVideo, TranscriptSegment


class ClipAnalyzer:
    """Scores transcript and visual signals to select short-form clip candidates."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def find_candidates(
        self,
        source_video: SourceVideo,
        transcript: list[TranscriptSegment],
    ) -> list[ClipCandidate]:
        """Return 35-60 second clips ranked by viral potential."""
        # TODO: Swap MockViralMomentAnalyzer for GeminiAnalyzer once provider prompts are ready.
        metadata = {
            "video_id": source_video.video_id,
            "original_url": source_video.url,
            "title": source_video.title,
            "duration": source_video.duration_seconds,
        }
        windows = [
            {
                "start": segment.start_seconds,
                "end": min(segment.start_seconds + 45, segment.end_seconds),
                "text": segment.text,
                "hook_text": segment.text[:240],
            }
            for segment in transcript
            if segment.end_seconds - segment.start_seconds >= 35
        ]
        return MockViralMomentAnalyzer().analyze_windows(windows, metadata)
