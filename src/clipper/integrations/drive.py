from clipper.config import Settings
from clipper.models import ClipRender


class GoogleDriveUploader:
    """Uploads finished clips to Google Drive."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def upload(self, clip: ClipRender) -> ClipRender:
        """Upload a clip and attach the resulting Drive file id."""
        # TODO: Implement Google Drive API auth and resumable upload.
        raise NotImplementedError("Google Drive upload integration is not implemented yet.")
