import argparse
from collections.abc import Sequence

from clipper.analysis.analyzer import ClipAnalyzer
from clipper.config import Settings, get_settings
from clipper.download import YouTubeDownloader
from clipper.integrations import AfterEffectsClient, GoogleDriveUploader, NotionLogger
from clipper.models import Job, JobStatus
from clipper.processing import VideoProcessor
from clipper.state import JobStore
from clipper.transcription import Transcriber


class ClipperPipeline:
    """Coordinates download, transcription, analysis, rendering, and publishing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = JobStore(settings)
        self.downloader = YouTubeDownloader(settings)
        self.transcriber = Transcriber(settings)
        self.analyzer = ClipAnalyzer(settings)
        self.processor = VideoProcessor(settings)
        self.after_effects = AfterEffectsClient(settings)
        self.drive = GoogleDriveUploader(settings)
        self.notion = NotionLogger(settings)

    def run(self, urls: Sequence[str]) -> Job:
        """Run the end-to-end local clip generation workflow."""
        self.settings.ensure_local_dirs()
        job = self.store.create(list(urls))

        try:
            for url in job.urls:
                source_video = self.downloader.download(url)
                job.source_videos.append(source_video)
                job.status = JobStatus.DOWNLOADED
                self.store.save(job)

                transcript = self.transcriber.transcribe(source_video)
                if source_video.video_id is None:
                    raise ValueError("Downloaded source video is missing a video_id.")
                job.transcript_segments[source_video.video_id] = transcript
                job.status = JobStatus.TRANSCRIBED
                self.store.save(job)

                candidates = self.analyzer.find_candidates(source_video, transcript)
                job.candidates.extend(candidates)
                job.status = JobStatus.ANALYZED
                self.store.save(job)

                for candidate in candidates:
                    render = self.processor.render_vertical_clip(source_video, candidate)
                    job.renders.append(render)

                job.status = JobStatus.RENDERED
                self.store.save(job)

            job.status = JobStatus.REVIEW_READY
            self.store.save(job)
            return job
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            # TODO: Persist failure details once JobStore is implemented.
            raise

    def publish_approved(self, job: Job) -> Job:
        """Send approved clips through finishing, upload, and metadata logging."""
        # TODO: Decide whether finishing happens before or after review in the UI.
        for clip in job.renders:
            if not clip.approved:
                continue
            finished_clip = self.after_effects.send_for_finishing(clip)
            uploaded_clip = self.drive.upload(finished_clip)
            self.notion.log_clip(uploaded_clip)

        job.status = JobStatus.LOGGED
        self.store.save(job)
        return job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AI Auto Clipper pipeline skeleton.")
    parser.add_argument("urls", nargs="+", help="One or more YouTube URLs to process.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = ClipperPipeline(get_settings())
    pipeline.run(args.urls)


if __name__ == "__main__":
    main()
