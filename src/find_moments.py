import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find viral short-form moments from a transcript.")
    parser.add_argument("raw_video_dir", help="Directory containing transcript.json and metadata.json.")
    parser.add_argument("--max-candidates", type=int, default=10, help="Maximum candidates to return.")
    parser.add_argument("--provider", choices=["mock", "gemini"], help="Override ANALYZER_PROVIDER for this run.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    raw_video_dir = Path(args.raw_video_dir)
    transcript_path = raw_video_dir / "transcript.json"
    metadata_path = raw_video_dir / "metadata.json"

    from clipper.analysis import find_clip_candidates

    candidates = find_clip_candidates(
        str(transcript_path),
        str(metadata_path),
        max_candidates=args.max_candidates,
        provider=args.provider,
    )
    print(json.dumps([candidate.model_dump(mode="json") for candidate in candidates], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
