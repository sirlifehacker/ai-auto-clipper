from clipper.config import Settings
from clipper.models import ClipRender


class AfterEffectsClient:
    """Future MCP adapter for sending approved clips to After Effects."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_for_finishing(self, clip: ClipRender) -> ClipRender:
        """Send a clip to After Effects for overlays, motion graphics, and VFX."""
        # TODO: Implement After Effects MCP calls once the MCP contract is defined.
        # Expected behavior:
        # - create/open an AE project
        # - import rendered clip
        # - apply text overlays and motion graphics
        # - export finished clip
        raise NotImplementedError("After Effects MCP integration is not implemented yet.")
