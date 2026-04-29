import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trim ranked clip candidates with FFmpeg.")
    parser.add_argument("candidates_path", help="Path to ranked_clip_candidates.json.")
    parser.add_argument("--source-video", help="Override source video path. Defaults to source.mp4 beside candidates JSON.")
    parser.add_argument("--output-dir", help="Override output clip directory.")
    parser.add_argument("--limit", type=int, help="Only trim the first N candidates.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    candidates_path = Path(args.candidates_path)
    candidates = _load_candidates(candidates_path)

    source_video_path = Path(args.source_video) if args.source_video else candidates_path.parent / "source.mp4"
    video_id = candidates[0].source_video_id if candidates else candidates_path.parent.name
    output_dir = Path(args.output_dir) if args.output_dir else Path("data/processed") / video_id / "clips"

    from clipper.processing.ffmpeg import trim_clip

    selected_candidates = candidates[: args.limit] if args.limit else candidates
    for candidate in selected_candidates:
        trim_clip(str(source_video_path), candidate, str(output_dir))

    _save_candidates(candidates_path, candidates)
    print(json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2, ensure_ascii=False))


def _load_candidates(candidates_path: Path):
    from clipper.models import ClipCandidate

    if not candidates_path.exists():
        raise FileNotFoundError(f"Candidates file not found: {candidates_path}")
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Candidates JSON must contain a list.")
    return [ClipCandidate.model_validate(item) for item in payload]


def _save_candidates(candidates_path: Path, candidates) -> None:
    candidates_path.write_text(
        json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
