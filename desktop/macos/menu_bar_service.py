"""
macOS menu bar service — entry point for the Lightworks Pro daemon on macOS.
Uses rumps for the menu bar icon and Quartz for non-intercepting global hotkeys.
"""
from __future__ import annotations

import asyncio
import logging
import threading

import rumps
from Quartz import (
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    kCGEventKeyDown,
    kCGHIDEventTap,
    kCGHeadInsertEventTap,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskAlternate,
)

from core.voice.tts_engine import TTSEngine
from core.voice.stt_engine import STTEngine
from core.consent.state_machine import ConsentFSM
from core.meeting.orchestrator import MeetingOrchestrator
from core.email_intel.suite import EmailIntelSuite
from core.notifications.engine import NotificationEngine

log = logging.getLogger(__name__)

KEY_L = 37
KEY_I = 34
KEY_M = 46

CMD_ALT = kCGEventFlagMaskCommand | kCGEventFlagMaskAlternate


class MacMenuBarService(rumps.App):
    def __init__(self, config: dict) -> None:
        super().__init__("LW", title="◉")
        self._config = config
        self._loop = asyncio.new_event_loop()
        self._tts = TTSEngine()
        self._stt = STTEngine(model_size=config.get("whisper_model", "base"))
        self._fsm = ConsentFSM(tts=self._tts, stt=self._stt)
        self._notification_engine = NotificationEngine(tts=self._tts)
        self._meeting_orchestrator = None
        self._email_suite = None

        self.menu = [
            rumps.MenuItem("Lightworks Pro", callback=None),
            None,
            rumps.MenuItem("Read Inbox", callback=self._menu_inbox),
            rumps.MenuItem("Next Meeting", callback=self._menu_meetings),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

    def _menu_inbox(self, _) -> None:
        if self._email_suite:
            asyncio.run_coroutine_threadsafe(
                self._email_suite.announce_inbox(), self._loop
            )

    def _menu_meetings(self, _) -> None:
        asyncio.run_coroutine_threadsafe(
            self._tts.speak("Checking your calendar.", priority="normal"), self._loop
        )

    @rumps.timer(1)
    def _startup(self, _) -> None:
        """Called once after the run loop starts."""
        self._startup.stop()

        loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="lw-asyncio"
        )
        loop_thread.start()

        asyncio.run_coroutine_threadsafe(self._init_services(), self._loop)

        hotkey_thread = threading.Thread(
            target=self._hotkey_listener, daemon=True, name="lw-hotkeys"
        )
        hotkey_thread.start()

    async def _init_services(self) -> None:
        await self._tts.speak(
            "Lightworks Pro is running. Press Command Option L to give a command.",
            priority="normal",
        )
        if self._config.get("microsoft_client_id"):
            from core.integrations.microsoft.auth import MicrosoftAuth
            from core.integrations.microsoft.graph_client import GraphClient
            auth = MicrosoftAuth(self._config["microsoft_client_id"])
            graph = GraphClient(auth)
            self._meeting_orchestrator = MeetingOrchestrator(self._fsm, self._tts, graph)
            self._email_suite = EmailIntelSuite(self._fsm, self._tts, self._stt, graph)
            asyncio.create_task(self._meeting_orchestrator.run())

        asyncio.create_task(self._notification_engine.run())

    def _hotkey_listener(self) -> None:
        """CGEvent tap — passive listener that does NOT consume events."""
        service = self

        def callback(proxy, event_type, event, refcon):
            if event_type == kCGEventKeyDown:
                from Quartz import CGEventGetIntegerValueField, kCGKeyboardEventKeycode, CGEventGetFlags
                keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                flags = CGEventGetFlags(event) & 0xFFFFFF   # strip reserved bits
                if flags == CMD_ALT:
                    if keycode == KEY_L:
                        asyncio.run_coroutine_threadsafe(service._on_listen(), service._loop)
                    elif keycode == KEY_I and service._email_suite:
                        asyncio.run_coroutine_threadsafe(service._email_suite.announce_inbox(), service._loop)
            return event   # return the event unmodified — passive tap

        event_mask = CGEventMaskBit(kCGEventKeyDown)
        tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            0,   # passive — does not consume
            event_mask,
            callback,
            None,
        )
        if not tap:
            log.error("Could not create CGEvent tap — check Accessibility permissions")
            return

        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, "kCFRunLoopDefaultMode")
        CGEventTapEnable(tap, True)
        CFRunLoopRun()

    async def _on_listen(self) -> None:
        await self._tts.speak("Listening.", priority="alert")
        utterance = await self._stt.listen_once()
        log.info("Command heard: %r", utterance)
