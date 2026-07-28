"""Frozen User-Agent values shared by playback capability and clients."""

from __future__ import annotations

from typing import Literal

PlaybackPlatform = Literal["windows", "harmonyos"]

WINDOWS_USER_AGENT = "SakuraPlayer/1.0 (Windows; x64)"
HARMONYOS_USER_AGENT = "SakuraPlayer/1.0 (HarmonyOS; API 24)"

_USER_AGENTS: dict[PlaybackPlatform, str] = {
    "windows": WINDOWS_USER_AGENT,
    "harmonyos": HARMONYOS_USER_AGENT,
}


def user_agent_for(platform: PlaybackPlatform) -> str:
    try:
        return _USER_AGENTS[platform]
    except KeyError as error:
        raise ValueError("unsupported playback platform") from error


__all__ = [
    "HARMONYOS_USER_AGENT",
    "PlaybackPlatform",
    "WINDOWS_USER_AGENT",
    "user_agent_for",
]
