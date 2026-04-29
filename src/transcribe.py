import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe a downloaded source.mp4 file.")
    parser.add_argument("video_path", help="Path to source.mp4.")
    parser.add_argument(
        "--output-dir",
        help="Directory for transcript.json and transcript.txt. Defaults to the video file directory.",
    )
    parser.add_argument("--force", action="store_true", help="Re-transcribe even if transcript files already exist.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    video_path = Path(args.video_path)
    output_dir = Path(args.output_dir) if args.output_dir else video_path.parent

    from clipper.transcription import transcribe_video

    result = transcribe_video(str(video_path), str(output_dir), force=args.force)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
