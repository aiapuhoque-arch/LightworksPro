"""
Meeting Orchestrator — detects upcoming meetings, identifies host vs. participant role,
and (after explicit consent) launches the meeting client via OS deep link.

Supports: Microsoft Teams, Zoom, Webex, Google Meet.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

from core.consent.state_machine import ConsentFSM, ConsentRequest

log = logging.getLogger(__name__)

ALERT_MINUTES = [10, 5]          # announce at each threshold
CHECK_INTERVAL_SECONDS = 20
START_WINDOW_SECONDS = 90        # fire "starting now" within 90 s of scheduled start


class MeetingOrchestrator:
    """
    Polls calendar sources for imminent meetings and initiates the consent loop.

    Sources must implement `.upcoming_events(count)` returning objects with:
      .subject, .start, .end, .is_organizer, .deep_link, .platform
    Sources may optionally implement `.set_presence(availability, activity)`.
    """

    def __init__(self, consent_fsm: ConsentFSM, tts, stt, *sources) -> None:
        self._fsm = consent_fsm
        self._tts = tts
        self._stt = stt
        self._sources = sources
        self._alerted: set[str] = set()
        self.in_meeting: bool = False
        self.current_platform: Optional[str] = None
        self._presence_reset_task: Optional[asyncio.Task] = None

    async def run(self) -> None:
        """Poll loop — run as an asyncio task alongside other services."""
        while True:
            await self._check_all()
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def announce_next_meeting(self) -> None:
        """Fetch and speak a summary of the next upcoming meeting on demand."""
        all_events: list = []
        for source in self._sources:
            try:
                events = await asyncio.get_running_loop().run_in_executor(
                    None, lambda s=source: s.upcoming_events(10)
                )
                all_events.extend(events)
            except Exception:
                log.exception("Failed to fetch events from %s", type(source).__name__)

        now = datetime.now(timezone.utc)
        future = sorted(
            (e for e in all_events if e.start > now),
            key=lambda e: e.start,
        )

        if not future:
            await self._tts.speak(
                "No upcoming meetings in the next 24 hours.", priority="normal"
            )
            return

        event = future[0]
        minutes = int((event.start - now).total_seconds() / 60)
        hours, mins = divmod(minutes, 60)

        if hours > 0:
            time_str = f"{hours} hour{'s' if hours != 1 else ''}"
            if mins:
                time_str += f" and {mins} minute{'s' if mins != 1 else ''}"
        else:
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"

        role = "host" if event.is_organizer else "participant"
        platform_name = (event.platform or "meeting").replace("_", " ").title()

        await self._tts.speak(
            f"Your next meeting is in {time_str}. "
            f"{platform_name}: {event.subject}. You are the {role}.",
            priority="normal",
        )

    async def _check_all(self) -> None:
        now = datetime.now(timezone.utc)
        for source in self._sources:
            try:
                events = await asyncio.get_running_loop().run_in_executor(
                    None, lambda s=source: s.upcoming_events(10)
                )
            except Exception:
                log.exception("Failed to fetch events from %s", type(source).__name__)
                continue

            for event in events:
                # Skip events that ended already
                if hasattr(event, "end") and event.end and event.end < now:
                    continue

                starts_in = event.start - now
                seconds_until = starts_in.total_seconds()
                minutes_until = seconds_until / 60

                # ── "Starting now" window: ±90 s around scheduled start ────────
                # Fires once per event regardless of prior advance alerts.
                # Hosts are auto-joined; participants are asked.
                start_key = f"{event.id}_start"
                if (start_key not in self._alerted and
                        -START_WINDOW_SECONDS <= seconds_until <= START_WINDOW_SECONDS):
                    self._alerted.add(start_key)
                    asyncio.create_task(self._handle_start(event))
                    continue

                # Skip events already past their start window
                if minutes_until < 0:
                    continue

                # ── Advance alerts at each threshold ──────────────────────────
                for threshold in sorted(ALERT_MINUTES, reverse=True):
                    alert_key = f"{event.id}_{threshold}min"
                    if alert_key in self._alerted:
                        continue
                    if minutes_until <= threshold:
                        self._alerted.add(alert_key)
                        asyncio.create_task(self._handle_event(event, starts_in))
                        break   # one alert per event per check cycle

    # Config hook — tray service sets this to True to enable auto-mute on join
    auto_mute_on_join: bool = False

    async def _handle_start(self, event) -> None:
        """
        Fires when a meeting reaches its scheduled start time (±90 s window).

        Both host and participant: announces the meeting, waits 15 s for a
        "cancel" voice command, then auto-joins if no cancellation is heard.
        """
        platform_name = (event.platform or "meeting").replace("_", " ").title()
        join_url = getattr(event, "deep_link", None) or getattr(event, "meeting_url", None)
        role_label = "host" if event.is_organizer else "participant"

        await self._tts.speak(
            f"Your {platform_name} meeting is starting now: {event.subject}. "
            f"Joining as {role_label} in 15 seconds. Say cancel to abort.",
            priority="alert",
        )

        # Brief gap so speaker audio fully decays before the mic opens.
        # Without this, JAWS or speaker echo can trigger a false cancellation.
        await asyncio.sleep(0.5)

        # Listen for up to 15 s — auto-join unless the user says cancel.
        # listen_once enforces max_secs internally; no asyncio.wait_for needed.
        # Only "cancel", "don't", "not now" are accepted — "stop", "no", "skip"
        # are excluded because JAWS/screen readers say them too often, causing
        # false cancellations when JAWS reads Teams button labels or notifications.
        cancelled = False
        utterance = await self._stt.listen_once(max_secs=15.0)
        if utterance:
            utter_low = utterance.strip().lower()
            if any(w in utter_low for w in ("cancel", "don't", "not now")):
                cancelled = True
                await self._tts.speak("Meeting join cancelled.", priority="normal")

        if cancelled:
            pass
        elif self.in_meeting:
            await self._tts.speak(
                f"You are already in a meeting. Cannot auto-join as {role_label}.",
                priority="normal",
            )
        elif join_url:
            await self._do_launch(event)
        else:
            await self._tts.speak(
                "No join link found. Open the meeting manually.",
                priority="normal",
            )

    async def _handle_event(self, event, starts_in: timedelta) -> None:
        """
        Advance alert — fires at 10 min and 5 min before the meeting.
        Announce only — joining happens at start time via _handle_start.
        """
        minutes = max(1, int(starts_in.total_seconds() / 60))
        role = "host" if event.is_organizer else "participant"
        platform_name = (event.platform or "meeting").replace("_", " ").title()

        agenda = (getattr(event, "body_preview", "") or "").strip()
        agenda_spoken = f" Agenda: {agenda[:200]}." if agenda else ""

        await self._tts.speak(
            f"Reminder: you have a {platform_name} meeting in {minutes} "
            f"minute{'s' if minutes != 1 else ''} as {role}. "
            f"Subject: {event.subject}.{agenda_spoken}",
            priority="alert",
        )

    async def _do_launch(self, event) -> None:
        """Open the meeting client, set presence, schedule presence reset."""
        join_url = getattr(event, "deep_link", None) or getattr(event, "meeting_url", None)
        platform_name = (event.platform or "meeting").replace("_", " ").title()

        if not join_url:
            await self._tts.speak(
                "No join link available. Open the meeting manually.",
                priority="normal",
            )
            return

        await asyncio.get_running_loop().run_in_executor(
            None, lambda: _launch_deep_link(join_url)
        )
        if event.platform == "teams":
            asyncio.create_task(self._auto_join_lobby())

        self.in_meeting = True
        self.current_platform = event.platform

        for src in self._sources:
            if hasattr(src, "set_presence"):
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda s=src: s.set_presence("Busy", "InAMeeting")
                    )
                except Exception:
                    log.exception("Failed to set presence on %s", type(src).__name__)

        await self._tts.speak(f"{platform_name} is opening. Good luck.", priority="normal")

        if self.auto_mute_on_join and event.platform in ("teams", "zoom"):
            asyncio.create_task(self._auto_mute_after_join(event.platform))

        if hasattr(event, "end") and event.end:
            reset_delay = (event.end - datetime.now(timezone.utc)).total_seconds() + 300
            if reset_delay > 0:
                if self._presence_reset_task:
                    self._presence_reset_task.cancel()
                self._presence_reset_task = asyncio.create_task(
                    self._reset_presence_after(reset_delay)
                )

    async def _auto_join_lobby(self) -> None:
        """
        After the Teams deep link is opened, the pre-join lobby screen appears.
        Wait briefly for it to render, then click 'Join now' via UIA.
        """
        await asyncio.sleep(4.0)
        from core.meeting import controls
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(
            None, lambda: controls.click_teams_join_now(timeout=15.0)
        )
        if not ok:
            log.warning("Could not auto-click 'Join now' on Teams pre-join screen")
            await self._tts.speak(
                "Teams pre-join screen is open. Please press Join now to enter the meeting.",
                priority="normal",
            )

    async def _auto_mute_after_join(self, platform: str) -> None:
        """Wait for the meeting app to open, then send the mute hotkey."""
        await asyncio.sleep(3.0)   # give the app time to launch and connect
        from core.meeting import controls
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(None, lambda: controls.mute_toggle(platform))
        if ok:
            await self._tts.speak("Microphone muted on join.", priority="normal")
        else:
            log.warning("Auto-mute: could not find %s window after join", platform)

    async def _reset_presence_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        self.in_meeting = False
        self.current_platform = None
        for src in self._sources:
            if hasattr(src, "set_presence"):
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda s=src: s.set_presence("Available", "Available")
                    )
                except Exception:
                    log.exception("Failed to reset presence on %s", type(src).__name__)


def _launch_deep_link(url: str) -> None:
    """
    Open a meeting URL via the OS default handler.
    On Windows this resolves msteams://, zoommtg://, etc. to the installed app.
    On macOS, 'open' does the same. Falls back to https:// in the default browser.
    """
    system = platform.system()
    log.info("Launching: %s", url)
    if system == "Windows":
        import os
        os.startfile(url)   # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["open", url], check=False)
    else:
        subprocess.run(["xdg-open", url], check=False)
