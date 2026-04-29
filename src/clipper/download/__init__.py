__all__ = ["YouTubeDownloader", "download_video", "download_videos_from_file"]


def __getattr__(name: str):
    if name in {"YouTubeDownloader", "download_video"}:
        from clipper.download.youtube import YouTubeDownloader, download_video

        return {"YouTubeDownloader": YouTubeDownloader, "download_video": download_video}[name]
    if name == "download_videos_from_file":
        from clipper.download.batch import download_videos_from_file

        return download_videos_from_file
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
