"""
Voice reminder engine — parse natural-language time expressions and schedule
asyncio tasks that speak the reminder when the time arrives.

Supported formats:
  "remind me in 5 minutes about the call"
  "remind me in half an hour about lunch"
  "remind me in 2 hours about the report"
  "remind me at 3pm about the standup"
  "remind me at 14:30 about the meeting"
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ── Time expression patterns ──────────────────────────────────────────────────
_PATTERNS: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"\bin\s+(\d+)\s+minute", re.I),
     lambda m: int(m.group(1)) * 60),

    (re.compile(r"\bin\s+half\s+an?\s+hour", re.I),
     lambda m: 1800),

    (re.compile(r"\bin\s+an?\s+hour", re.I),
     lambda m: 3600),

    (re.compile(r"\bin\s+(\d+)\s+and\s+a\s+half\s+hours?", re.I),
     lambda m: int(m.group(1)) * 3600 + 1800),

    (re.compile(r"\bin\s+(\d+)\s+hours?", re.I),
     lambda m: int(m.group(1)) * 3600),

    # "at 3pm", "at 3:30pm", "at 14:30"
    (re.compile(r"\bat\s+(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?", re.I),
     None),   # handled separately in _parse
]

_TOPIC_RE = re.compile(r"\babout\s+(.+)$", re.I)


def _seconds_from_at_match(m: re.Match) -> int | None:
    """Convert an 'at HH[:MM] [am|pm]' match to seconds from now."""
    hour   = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm   = (m.group(3) or "").lower()

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    if hour > 23 or minute > 59:
        return None

    now    = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)   # assume tomorrow if time has passed

    return int((target - now).total_seconds())


def _parse(utterance: str) -> tuple[int | None, str]:
    """
    Return (delay_seconds, topic) from a reminder utterance.
    delay_seconds is None if no valid time expression was found.
    """
    topic_m = _TOPIC_RE.search(utterance)
    topic   = topic_m.group(1).strip() if topic_m else "your reminder"

    for pattern, handler in _PATTERNS:
        m = pattern.search(utterance)
        if m:
            if handler is None:
                seconds = _seconds_from_at_match(m)
            else:
                seconds = handler(m)
            return seconds, topic

    return None, topic


def _seconds_to_spoken(seconds: int) -> str:
    minutes = seconds // 60
    if minutes >= 60:
        hours, mins = divmod(minutes, 60)
        s = f"{hours} hour{'s' if hours != 1 else ''}"
        if mins:
            s += f" and {mins} minute{'s' if mins != 1 else ''}"
        return s
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


class ReminderEngine:
    """
    Schedules asyncio tasks that fire TTS announcements at the requested time.
    All tasks are fire-and-forget; active tasks are tracked so the engine can
    report the count if asked.
    """

    def __init__(self, tts) -> None:
        self._tts = tts
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def schedule(self, utterance: str) -> str:
        """
        Parse utterance and schedule the reminder.
        Returns a spoken feedback string (success or failure message).
        """
        seconds, topic = _parse(utterance)

        if seconds is None:
            return (
                "I didn't understand the time. "
                "Try saying: remind me in 5 minutes about the meeting, "
                "or remind me at 3 pm about the call."
            )

        if seconds <= 0:
            return "That time has already passed. Please try again."

        task = asyncio.create_task(self._fire(seconds, topic))
        self._tasks = [t for t in self._tasks if not t.done()]
        self._tasks.append(task)

        return f"Reminder set. I will remind you about {topic} in {_seconds_to_spoken(seconds)}."

    def active_count(self) -> int:
        self._tasks = [t for t in self._tasks if not t.done()]
        return len(self._tasks)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _fire(self, delay: float, topic: str) -> None:
        await asyncio.sleep(delay)
        await self._tts.speak(f"Reminder: {topic}.", priority="alert")
