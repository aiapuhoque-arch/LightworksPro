"""
Voice Notification Engine — real-time alerts for incoming emails and meeting changes.
Uses Microsoft Graph $delta / Google push notifications for low-latency delivery.
Audio ducking is applied when Lightworks Pro speaks (media volume lowered, AT stream untouched).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Awaitable

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30    # fallback when push notifications unavailable


class NotificationEngine:
    """
    Subscribes to change notifications from email and calendar sources,
    announces them via TTS with audio ducking.
    """

    def __init__(self, tts, audio_ducker=None) -> None:
        self._tts = tts
        self._ducker = audio_ducker     # Optional[AudioDucker] from native module
        self._handlers: list[Callable[[], Awaitable[list]]] = []
        self._seen_ids: set[str] = set()

    def register_source(self, poll_fn: Callable[[], Awaitable[list]]) -> None:
        """Register an async function that returns a list of new notification objects."""
        self._handlers.append(poll_fn)

    async def run(self) -> None:
        while True:
            await self._poll_all()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _poll_all(self) -> None:
        for handler in self._handlers:
            try:
                items = await handler()
                for item in items:
                    if item.id not in self._seen_ids:
                        self._seen_ids.add(item.id)
                        await self._announce(item)
            except Exception:
                log.exception("Notification poll error")

    async def _announce(self, item) -> None:
        text = _build_announcement(item)
        if not text:
            return
        log.info("ANNOUNCE: %s", text)
        if self._ducker:
            await self._ducker.duck()
        try:
            await self._tts.speak(text, priority="alert")
        finally:
            if self._ducker:
                await self._ducker.unduck()


def _build_announcement(item) -> str:
    """Build a spoken string from any notification-like object."""
    item_type = type(item).__name__.lower()

    if "email" in item_type or "message" in item_type or "gmail" in item_type:
        importance = "High priority. " if getattr(item, "is_high_priority", False) or getattr(item, "is_important", False) else ""
        return (
            f"New email. {importance}"
            f"From {getattr(item, 'sender_name', 'someone')}. "
            f"Subject: {getattr(item, 'subject', 'no subject')}."
        )

    if "event" in item_type or "meeting" in item_type:
        return (
            f"Calendar update. {getattr(item, 'subject', getattr(item, 'summary', 'Meeting'))} "
            f"has been modified."
        )

    return ""
