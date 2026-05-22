"""
Windows audio ducking — lowers per-session media volume while Lightworks Pro speaks,
then restores it. Uses pycaw (Python Core Audio Windows) to reach WASAPI directly.

AT processes (JAWS, NVDA, ZoomText, Fusion) are explicitly skipped so their audio
paths are never touched.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)

AT_PROCESS_NAMES = frozenset({
    "jfw.exe",       # JAWS
    "nvda.exe",      # NVDA
    "zoomtext.exe",  # ZoomText
    "fusion.exe",    # Fusion
    "magnify.exe",   # Windows Magnifier
    "narrator.exe",  # Windows Narrator
})


class AudioDucker:
    """
    Context-manager-style audio ducker.

    Usage:
        async with AudioDucker(duck_to=0.2):
            await tts.speak(...)

    Or explicit:
        await ducker.duck()
        await tts.speak(...)
        await ducker.unduck()
    """

    def __init__(self, duck_to: float = 0.2) -> None:
        self._duck_to = max(0.0, min(1.0, duck_to))
        self._saved: dict[int, float] = {}   # pid → original volume

    async def __aenter__(self) -> "AudioDucker":
        await self.duck()
        return self

    async def __aexit__(self, *_) -> None:
        await self.unduck()

    async def duck(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._duck_sync)

    async def unduck(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._unduck_sync)

    def _duck_sync(self) -> None:
        sessions = _get_sessions()
        for pid, name, volume_iface in sessions:
            if name.lower() in AT_PROCESS_NAMES:
                continue
            try:
                current = volume_iface.GetMasterVolume()
                if current > self._duck_to:
                    self._saved[pid] = current
                    volume_iface.SetMasterVolume(self._duck_to, None)
            except Exception:
                log.debug("Could not duck pid=%d (%s)", pid, name)

    def _unduck_sync(self) -> None:
        if not self._saved:
            return
        sessions = _get_sessions()
        session_map = {pid: iface for pid, _, iface in sessions}
        for pid, original in list(self._saved.items()):
            if pid in session_map:
                try:
                    session_map[pid].SetMasterVolume(original, None)
                except Exception:
                    log.debug("Could not restore volume for pid=%d", pid)
        self._saved.clear()


def _get_sessions() -> list[tuple[int, str, object]]:
    """Return (pid, process_name, ISimpleAudioVolume) for all active audio sessions."""
    try:
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        from comtypes import CLSCTX_ALL

        results = []
        for session in AudioUtilities.GetAllSessions():
            if session.Process is None:
                continue
            pid = session.Process.pid
            name = session.Process.name()
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            results.append((pid, name, volume))
        return results
    except ImportError:
        log.warning("pycaw not installed — audio ducking disabled. Run: pip install pycaw")
        return []
    except Exception:
        log.exception("Failed to enumerate audio sessions")
        return []
