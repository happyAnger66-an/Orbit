"""CLI program context"""

from typing import List


class ProgramContext:
    """CLI program context, similar to OpenClaw's ProgramContext"""

    def __init__(self, version: str):
        self.program_version = version
        self._channel_options: List[str] = []

    @property
    def channel_options(self) -> List[str]:
        """Get available channel options"""
        if not self._channel_options:
            # TODO: Resolve from config/plugins
            self._channel_options = ["telegram", "whatsapp", "discord", "slack"]
        return self._channel_options

    @property
    def message_channel_options(self) -> str:
        """Get message channel options as pipe-separated string"""
        return "|".join(self.channel_options)

    @property
    def agent_channel_options(self) -> str:
        """Get agent channel options as pipe-separated string"""
        return "|".join(["last"] + self.channel_options)


def create_program_context(version: str) -> ProgramContext:
    """Create a new program context"""
    return ProgramContext(version)
