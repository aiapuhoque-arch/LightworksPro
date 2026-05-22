"""
Windows system tray service — entry point for the Lightworks Pro desktop daemon.

Threading model:
  main thread  — pystray icon (required by Win32 message pump)
  lw-asyncio   — asyncio event loop (all coroutines, services, consent FSM)
  lw-hotkeys   — Win32 RegisterHotKey message loop (non-intercepting)
  lw-tts       — SAPI5 worker (COM STA — must stay on one thread)

Startup order:
  1. Start asyncio loop thread.
  2. Start hotkey thread (registers keys, sets _hotkeys_ready event).
  3. Schedule _start_services (waits for _hotkeys_ready before speaking).
  4. Run tray icon on main thread (blocks until quit).
"""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import logging
import re
import threading
from datetime import datetime, timezone, timedelta
from typing import Callable

import pystray
from PIL import Image, ImageDraw

import winsound

from core.voice.tts_engine import TTSEngine
from core.voice.stt_engine import STTEngine
from core.consent.state_machine import ConsentFSM
from core.meeting.orchestrator import MeetingOrchestrator
from core.email_intel.suite import EmailIntelSuite
from core.notifications.engine import NotificationEngine
from core.reminders.engine import ReminderEngine
from core.todo.engine import TodoEngine
from core.system.weather import WeatherService
from core.system import status as sys_status

log = logging.getLogger(__name__)

# Win32 constants
MOD_ALT   = 0x0001
MOD_CTRL  = 0x0002
MOD_SHIFT = 0x0004
WM_HOTKEY = 0x0312

# Hotkey definitions — (id, modifiers, vk_code, spoken_label)
# Ctrl+Shift+Fx avoids conflicts with JAWS / NVDA.
HOTKEY_LISTEN     = 1
HOTKEY_INBOX      = 2
HOTKEY_MEETINGS   = 3
HOTKEY_TEAMS_CALL = 4
HOTKEY_QUIT       = 5

HOTKEYS = [
    (HOTKEY_LISTEN,     MOD_CTRL | MOD_SHIFT, 0x70, "Control Shift F1"),   # F1
    (HOTKEY_INBOX,      MOD_CTRL | MOD_SHIFT, 0x71, "Control Shift F2"),   # F2
    (HOTKEY_MEETINGS,   MOD_CTRL | MOD_SHIFT, 0x72, "Control Shift F3"),   # F3
    (HOTKEY_TEAMS_CALL, MOD_CTRL | MOD_SHIFT, 0x73, "Control Shift F4"),   # F4
    (HOTKEY_QUIT,       MOD_CTRL | MOD_SHIFT, 0x74, "Control Shift F5"),   # F5
]

_active_service: "WindowsTrayService | None" = None

INCOMING_CALL_POLL_SECONDS = 3     # how often to check for ringing call windows

# Day-of-week name → weekday number (Mon=0)
_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _mute_guard_beep() -> None:
    """
    Mute Guard pulse — two short tones confirm the mute toggle without using TTS.
    AT-safe: winsound.Beep uses the system audio device non-exclusively and
    coexists with JAWS/NVDA which retain control of their own audio streams.
    The descending pair (high→low) signals "muted"; ascending (low→high) would
    signal "unmuted" — but since we cannot read app state reliably we always
    play the confirmation pair as a tactile-equivalent audio cue.
    """
    try:
        winsound.Beep(880, 100)
        winsound.Beep(660, 100)
    except Exception:
        pass


def _earcon_executing() -> None:
    """Short ascending pair — command received, now processing."""
    try:
        winsound.Beep(660, 60)
        winsound.Beep(880, 60)
    except Exception:
        pass


def _earcon_done() -> None:
    """Rising triple — action completed successfully."""
    try:
        winsound.Beep(880, 50)
        winsound.Beep(1100, 50)
        winsound.Beep(1320, 80)
    except Exception:
        pass


def _earcon_error() -> None:
    """Descending pair — action failed."""
    try:
        winsound.Beep(660, 100)
        winsound.Beep(440, 150)
    except Exception:
        pass


def _setup_user32() -> ctypes.WinDLL:
    u = ctypes.windll.user32
    HWND  = ctypes.wintypes.HWND
    BOOL  = ctypes.wintypes.BOOL
    UINT  = ctypes.wintypes.UINT
    INT   = ctypes.c_int
    PMSG  = ctypes.POINTER(ctypes.wintypes.MSG)
    u.RegisterHotKey.argtypes   = [HWND, INT, UINT, UINT]
    u.RegisterHotKey.restype    = BOOL
    u.UnregisterHotKey.argtypes = [HWND, INT]
    u.UnregisterHotKey.restype  = BOOL
    u.GetMessageW.argtypes      = [PMSG, HWND, UINT, UINT]
    u.GetMessageW.restype       = BOOL
    u.TranslateMessage.argtypes = [PMSG]
    u.TranslateMessage.restype  = BOOL
    u.DispatchMessageW.argtypes = [PMSG]
    u.DispatchMessageW.restype  = ctypes.wintypes.LPARAM
    return u


class WindowsTrayService:
    def __init__(self, config: dict) -> None:
        global _active_service
        _active_service = self
        self._config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tts = TTSEngine()
        self._stt = STTEngine(model_size=config.get("whisper_model", "small"))
        self._fsm = ConsentFSM(tts=self._tts, stt=self._stt)
        self._notification_engine = NotificationEngine(tts=self._tts)
        self._reminder_engine = ReminderEngine(tts=self._tts)
        self._weather_service = WeatherService(config)
        self._meeting_orchestrator: MeetingOrchestrator | None = None
        self._email_suite: EmailIntelSuite | None = None
        self._todo_engine: TodoEngine | None = None
        self._graph = None          # GraphClient — set in _start_services
        self._ms_auth = None
        self._icon: pystray.Icon | None = None
        self._registered: dict[int, str] = {}
        self._failed: dict[int, str] = {}
        self._hotkeys_ready = threading.Event()
        # Tracks caller keys already routed so we don't repeat the same ring
        self._announced_calls: set[str] = set()
        # Missed calls recorded this session: list of {"caller", "platform", "time"}
        self._missed_calls: list[dict] = []
        # In-memory contact index populated at startup for sub-50 ms lookups
        self._contact_cache: dict = {}

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="lw-asyncio"
        )
        loop_thread.start()
        hotkey_thread = threading.Thread(
            target=self._hotkey_loop, daemon=True, name="lw-hotkeys"
        )
        hotkey_thread.start()
        asyncio.run_coroutine_threadsafe(self._start_services(), self._loop)
        self._icon = self._build_tray_icon()
        self._icon.run()

    async def _start_services(self) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._hotkeys_ready.wait(timeout=3.0)
        )
        if self._registered:
            keys = ", ".join(self._registered.values())
            msg = f"Lightworks Pro is running. Active hotkeys: {keys}."
        else:
            msg = (
                "Lightworks Pro is running. "
                "Warning: no hotkeys could be registered. "
                "Use the tray icon menu instead."
            )
        if self._failed:
            failed = ", ".join(self._failed.values())
            msg += f" Could not register: {failed}."

        await self._tts.speak(msg, priority="normal")

        # Pre-load Whisper model in background so the first listen_once is instant
        self._stt.preload()

        graph = self._build_graph_client()
        if graph and self._ms_auth:
            if self._ms_auth.needs_sign_in():
                graph = await self._run_microsoft_sign_in()
        elif graph is None and self._config.get("microsoft_client_id", "").strip():
            pass
        else:
            log.info("No Microsoft credentials — running without calendar/email")

        if graph:
            self._graph = graph
            orch = MeetingOrchestrator(self._fsm, self._tts, self._stt, graph)
            orch.auto_mute_on_join = self._config.get("auto_mute_on_join", False)
            self._meeting_orchestrator = orch
            self._email_suite = EmailIntelSuite(self._fsm, self._tts, self._stt, graph)
            self._email_suite.verbosity = self._config.get("verbosity", "normal")
            self._todo_engine = TodoEngine(self._tts, self._stt, graph)
            asyncio.create_task(self._meeting_orchestrator.run(), name="meeting-orchestrator")
            asyncio.create_task(self._email_suite.run(), name="email-monitor")
            asyncio.create_task(self._preload_contacts(), name="contact-preload")
            log.info("Microsoft Graph integration active")

            # Personalised time-of-day greeting using the signed-in user's name
            try:
                loop = asyncio.get_running_loop()
                profile = await loop.run_in_executor(None, self._graph.get_me)
                first_name = (profile.get("displayName") or "").split()[0]
            except Exception:
                first_name = ""
            hour = datetime.now().hour
            time_of_day = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
            greeting = f"Good {time_of_day}"
            if first_name:
                greeting += f", {first_name}"
            await self._tts.speak(greeting + ".", priority="normal")

        asyncio.create_task(self._notification_engine.run(), name="notification-engine")
        asyncio.create_task(self._incoming_call_watcher(), name="incoming-call-watcher")

        # Detect and announce running screen readers
        srs = await asyncio.get_running_loop().run_in_executor(
            None, sys_status.detect_screen_readers
        )
        if srs:
            sr_list = " and ".join(srs)
            await self._tts.speak(
                f"{sr_list} detected. Lightworks Pro is running alongside your screen reader.",
                priority="normal",
            )

    async def _run_microsoft_sign_in(self):
        try:
            _spoken, flow = self._ms_auth.begin_device_flow()
        except Exception:
            log.exception("Could not start Microsoft sign-in")
            await self._tts.speak(
                "Could not start Microsoft sign-in. Check your Client ID in the config file.",
                priority="normal",
            )
            return None

        user_code  = flow.get("user_code", "")
        verify_url = flow.get("verification_uri", "https://login.microsoft.com/device")

        import webbrowser
        webbrowser.open(verify_url)

        clipboard_ok = False
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(user_code, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            clipboard_ok = True
        except Exception:
            log.exception("Could not copy sign-in code to clipboard")

        if clipboard_ok:
            instructions = (
                "Microsoft 365 sign-in required. "
                "Your browser has been opened to the Microsoft sign-in page. "
                "The sign-in code has been copied to your clipboard. "
                "Press Control V to paste the code, then press Enter. "
                "Sign in with your Microsoft 365 account. "
                "I will detect when you are finished automatically."
            )
        else:
            code_spelled = ",  ".join(list(user_code))
            instructions = (
                "Microsoft 365 sign-in required. "
                "Your browser has been opened to the Microsoft sign-in page. "
                f"Enter the code:  {code_spelled}.  "
                "Sign in with your Microsoft 365 account. "
                "I will detect when you are finished automatically."
            )

        await self._tts.speak(instructions, priority="alert")

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self._ms_auth.complete_device_flow(flow)
            )
        except Exception:
            log.exception("Microsoft sign-in failed or timed out")
            await self._tts.speak(
                "Microsoft sign-in was not completed. "
                "Restart Lightworks Pro to try again.",
                priority="alert",
            )
            return None

        await self._tts.speak(
            "Microsoft 365 connected. Calendar and email are now active.",
            priority="normal",
        )
        return self._build_graph_client()

    def _build_graph_client(self):
        client_id = self._config.get("microsoft_client_id", "").strip()
        if not client_id:
            return None
        try:
            from core.integrations.microsoft.auth import MicrosoftAuth
            from core.integrations.microsoft.graph_client import GraphClient
            auth = MicrosoftAuth(
                client_id=client_id,
                tenant_id=self._config.get("microsoft_tenant_id", "common"),
            )
            self._ms_auth = auth
            return GraphClient(auth)
        except Exception:
            log.exception("Failed to initialise Microsoft Graph client")
            return None

    async def _preload_contacts(self) -> None:
        """Build in-memory contact index at startup for sub-50 ms lookups."""
        if not self._graph:
            return
        try:
            loop = asyncio.get_running_loop()
            # Load all three sources in parallel: SharePoint directory, org Azure AD, People API
            people_task = loop.run_in_executor(None, lambda: self._graph.get_people(count=200))
            org_task    = loop.run_in_executor(None, lambda: self._graph._org_users_preload(count=500))
            sp_task     = loop.run_in_executor(None, lambda: self._graph.get_sharepoint_directory())
            people, org, sp = await asyncio.gather(people_task, org_task, sp_task, return_exceptions=True)

            merged: dict = {}

            # Step 1: People API — frequent contacts baseline
            for c in (people if isinstance(people, list) else []):
                key = (c.get("displayName") or "").lower()
                if key:
                    merged[key] = c

            # Step 2: Org Azure AD — overwrites People; preserve phone from People when missing
            for c in (org if isinstance(org, list) else []):
                key = (c.get("displayName") or "").lower()
                if not key:
                    continue
                existing = merged.get(key)
                entry = {**c}
                if existing and not entry.get("phone") and existing.get("phone"):
                    entry["phone"] = existing["phone"]
                merged[key] = entry

            # Step 3: SharePoint staff directory — HIGHEST priority for contact routing fields.
            # SharePoint is the curated IT staff list; its phone/extension/email override
            # whatever Azure AD or the People API returned (which can have corrupted UPNs).
            # Department and jobTitle are kept from the org entry when SharePoint lacks them.
            if isinstance(sp, list):
                for c in sp:
                    key = (c.get("displayName") or "").lower()
                    if not key:
                        continue
                    existing = merged.get(key)
                    if existing:
                        # Merge: org/People data as base, SharePoint wins on contact fields
                        entry = {**existing}
                        if c.get("phone"):
                            entry["phone"] = c["phone"]
                        if c.get("extension"):
                            entry["extension"] = c["extension"]
                        if c.get("emailAddress"):
                            entry["emailAddress"] = c["emailAddress"]
                        entry["_source"] = "sharepoint"
                        merged[key] = entry
                    else:
                        merged[key] = c

            self._contact_cache = merged
            log.info("Contact cache: %d entries loaded", len(self._contact_cache))
        except Exception:
            log.exception("Contact pre-cache failed — live lookups will be used")

        if not self._contact_cache:
            # Both People API and Outlook contacts book returned nothing.
            # Most likely cause: People.Read scope not consented in the Azure app registration.
            if self._ms_auth:
                consent_url = self._ms_auth.get_admin_consent_url()
                log.warning(
                    "Contact cache is empty. If contact search fails, run "
                    "scripts\\grant_admin_consent.py or visit: %s", consent_url
                )
            await self._tts.speak(
                "Note: contact directory is empty. "
                "If voice calling does not work, run the grant admin consent script "
                "from the scripts folder and restart.",
                priority="normal",
            )

    def _lookup_contact_cached(self, name: str, count: int = 3) -> list | None:
        """Return contacts matching `name` from the in-memory cache.
        Returns None when the cache has not been populated yet (caller should do a live search).
        """
        if not self._contact_cache:
            return None
        name_lower = name.lower()
        hits = [c for k, c in self._contact_cache.items() if name_lower in k]
        return hits[:count]

    # ------------------------------------------------------------------
    # Hotkey loop
    # ------------------------------------------------------------------

    def _hotkey_loop(self) -> None:
        user32 = _setup_user32()
        for hk_id, modifiers, vk, label in HOTKEYS:
            ok = user32.RegisterHotKey(None, hk_id, modifiers, vk)
            if ok:
                self._registered[hk_id] = label
            else:
                err = ctypes.windll.kernel32.GetLastError()
                self._failed[hk_id] = label
                log.error("RegisterHotKey FAILED: %s — WinError %d", label, err)

        self._hotkeys_ready.set()
        if not self._registered:
            return

        msg = ctypes.wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0:
                break
            if ret == -1:
                continue
            if msg.message == WM_HOTKEY:
                asyncio.run_coroutine_threadsafe(
                    self._on_hotkey(int(msg.wParam)), self._loop
                )
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        for hk_id, _, _, _ in HOTKEYS:
            user32.UnregisterHotKey(None, hk_id)

    # ------------------------------------------------------------------
    # Hotkey / menu action dispatch
    # ------------------------------------------------------------------

    async def _on_hotkey(self, hk_id: int) -> None:
        try:
            if hk_id == HOTKEY_LISTEN:
                await self._action_listen()
            elif hk_id == HOTKEY_INBOX:
                await self._action_inbox()
            elif hk_id == HOTKEY_MEETINGS:
                await self._action_meetings()
            elif hk_id == HOTKEY_TEAMS_CALL:
                await self._action_teams_call()
            elif hk_id == HOTKEY_QUIT:
                await self._tts.speak("Goodbye.", priority="alert")
                self._on_quit()
        except Exception:
            log.exception("Error handling hotkey %d", hk_id)

    # ── Listen (Ctrl+Shift+F1) ────────────────────────────────────────

    async def _action_listen(self) -> None:
        # Interrupt any ongoing speech so the prompt is heard immediately
        self._tts.interrupt()
        await asyncio.sleep(0.15)

        await self._tts.speak(
            "Listening. Say help to know all commands. You have 15 seconds.",
            priority="alert",
        )
        # Extra pause so TTS audio fully clears the mic before recording starts
        await asyncio.sleep(0.5)
        # listen_once gives a 15-second window with a ready-beep at the start
        utterance = await self._stt.listen_once()
        if utterance:
            await self._dispatch_command(utterance)
        else:
            await self._tts.speak(
                "I did not hear anything. "
                "Press Control Shift F1, wait for the beep, then speak clearly. "
                "You have 15 seconds.",
                priority="normal",
            )

    # ── Inbox (Ctrl+Shift+F2) ─────────────────────────────────────────

    async def _action_inbox(self) -> None:
        if self._email_suite:
            await self._email_suite.announce_inbox()
        elif self._config.get("microsoft_client_id", "").strip():
            await self._tts.speak(
                "Microsoft 365 is not signed in. Restart Lightworks Pro to try signing in again.",
                priority="normal",
            )
        else:
            await self._tts.speak(
                "Email is not configured. Run the register Azure app script to set up Microsoft 365.",
                priority="normal",
            )

    # ── Meetings (Ctrl+Shift+F3) ──────────────────────────────────────

    async def _action_meetings(self) -> None:
        if self._meeting_orchestrator:
            await self._tts.speak("Checking your calendar.", priority="normal")
            await self._meeting_orchestrator.announce_next_meeting()
        elif self._config.get("microsoft_client_id", "").strip():
            await self._tts.speak(
                "Microsoft 365 is not signed in. Restart Lightworks Pro to try signing in again.",
                priority="normal",
            )
        else:
            await self._tts.speak(
                "Calendar is not configured. Run the register Azure app script to set up Microsoft 365.",
                priority="normal",
            )

    # ── Teams Call (Ctrl+Shift+F4) ────────────────────────────────────

    async def _action_teams_call(self) -> None:
        """
        Dedicated Teams call hotkey.

        Flow:
          1. Short prompt + beep  →  user speaks
          2. Route to the right call action
          3. Each action announces who/what it will call before dialling.

        The Graph check is intentionally NOT here — extension and dial work
        without Microsoft 365.  Graph-dependent actions (call by name,
        conference call) do their own check and speak an error if needed.
        """
        self._tts.interrupt()
        await asyncio.sleep(0.15)

        # Short prompt so the beep fires within ~2 seconds — users speak
        # right after the beep, not after a 15-second menu recital.
        await self._tts.speak(
            "Teams call. Say call, video call, conference call, extension, or dial.",
            priority="alert",
        )
        await asyncio.sleep(0.3)

        utterance = await self._stt.listen_once(max_secs=10)
        if not utterance:
            await self._tts.speak(
                "I did not hear anything. Press Control Shift F4, "
                "wait for the beep, then speak.",
                priority="normal",
            )
            return

        await self._route_call_utterance(utterance)

    async def _route_call_utterance(self, utterance: str) -> None:
        """Parse a call utterance and dispatch to the right action."""
        text = utterance.lower().strip()
        digits_only = re.sub(r"\D", "", text)
        # True when the utterance contains no alphabetic characters — STT heard
        # only digits (e.g. "6312") because "extension" was clipped by noise.
        pure_digits = not re.search(r"[a-zA-Z]", text)

        if any(w in text for w in ("conference call", "group call",
                                    "call conference", "start a conference")):
            await self._action_conference_call(utterance)

        elif any(w in text for w in ("video call", "video chat",
                                      "start video", "video with")):
            await self._action_call_contact(utterance, with_video=True)

        elif any(w in text for w in ("extension", "ext ", "ext.",
                                      "call extension", "dial extension", "internal")):
            await self._action_call_extension(utterance)

        elif any(w in text for w in ("dial", "phone number")) or (
            len(digits_only) >= 7
        ):
            await self._action_call_number(utterance)

        elif pure_digits and 3 <= len(digits_only) <= 6:
            # STT dropped "extension" — bare 3–6 digit number is an extension,
            # not a contact name (too short for PSTN, no letters for a person).
            await self._action_call_extension(utterance)

        else:
            # "call John", "ring Sarah", or a bare name — treat as audio call
            await self._action_call_contact(utterance)

    # ── Cancel-window helper ──────────────────────────────────────────

    async def _listen_for_cancel(self) -> bool:
        """
        Open a short ~4 s listen window after announcing an action.
        Returns True if the user said stop/cancel/no (i.e. the action
        should be aborted), False if silence or anything else (proceed).
        """
        response = await self._stt.listen_command()
        if response and any(
            w in response.lower()
            for w in ("stop", "cancel", "no", "don't", "abort", "wait")
        ):
            await self._tts.speak("Cancelled.", priority="normal")
            return True
        return False

    # ── Voice test ────────────────────────────────────────────────────

    async def _action_test_voice(self) -> None:
        await self._tts.speak(
            "Lightworks Pro voice test. Text to speech is working correctly.",
            priority="alert",
        )

    # ── Meeting controls ──────────────────────────────────────────────

    def _active_meeting_platform(self) -> str:
        if self._meeting_orchestrator and self._meeting_orchestrator.current_platform in ("teams", "zoom"):
            return self._meeting_orchestrator.current_platform
        return "teams"

    async def _action_mute_toggle(self) -> None:
        from core.meeting import controls
        platform = self._active_meeting_platform()
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: controls.mute_toggle(platform)
        )
        if ok:
            # Mute Guard: two short tones (muted=low, unmuted=high) distinct from TTS.
            # winsound.Beep is synchronous and brief — run in executor to avoid blocking loop.
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: _mute_guard_beep()
            )
        else:
            await self._tts.speak(
                f"Could not find the {platform.title()} window. Make sure it is open.",
                priority="normal",
            )

    async def _action_leave_meeting(self) -> None:
        from core.meeting import controls
        platform = self._active_meeting_platform()
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: controls.leave_meeting(platform)
        )
        if ok:
            if self._meeting_orchestrator:
                self._meeting_orchestrator.in_meeting = False
                self._meeting_orchestrator.current_platform = None
            await self._tts.speak("Left the meeting.", priority="normal")
        else:
            await self._tts.speak(
                f"Could not find the {platform.title()} window. Make sure it is open.",
                priority="normal",
            )

    async def _action_raise_hand(self) -> None:
        from core.meeting import controls
        platform = self._active_meeting_platform()
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: controls.raise_hand(platform)
        )
        if ok:
            await self._tts.speak("Hand raised.", priority="normal")
        else:
            await self._tts.speak(f"Could not find the {platform.title()} window.", priority="normal")

    async def _action_camera_toggle(self) -> None:
        from core.meeting import controls
        platform = self._active_meeting_platform()
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: controls.camera_toggle(platform)
        )
        if ok:
            await self._tts.speak("Camera toggled.", priority="normal")
        else:
            await self._tts.speak(f"Could not find the {platform.title()} window.", priority="normal")

    # ── Outgoing Teams calls ──────────────────────────────────────────

    async def _disambiguate_contact(self, results: list[dict]) -> dict | None:
        """
        If the top two results are clearly different people, ask which one.
        Returns the chosen contact dict, or None if the user cancelled.
        """
        if len(results) == 1:
            return results[0]
        first  = results[0].get("displayName", "")
        second = results[1].get("displayName", "")
        # Same last name → almost certainly the same person; pick first
        if first.split()[-1].lower() == second.split()[-1].lower():
            return results[0]
        dept0 = results[0].get("department", results[0].get("jobTitle", ""))
        dept1 = results[1].get("department", results[1].get("jobTitle", ""))
        d0 = f" from {dept0}" if dept0 else ""
        d1 = f" from {dept1}" if dept1 else ""
        await self._tts.speak(
            f"Two people found: {first}{d0}, or {second}{d1}. Say first or second.",
            priority="normal",
        )
        choice = await self._stt.listen_command()
        c = (choice or "").lower()
        if "second" in c or (second.split() and second.split()[0].lower() in c):
            return results[1]
        return results[0]   # default to first if unclear

    async def _action_call_contact(self, utterance: str, with_video: bool = False) -> None:
        """Look up a contact by name and dial them on Teams (audio or video)."""
        if not self._graph:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return

        import re as _re
        m = _re.search(
            r"(?:"
            r"video\s+call|video\s+chat|start\s+video\s+(?:with)?"
            r"|audio\s+call|teams\s+call"
            r"|start\s+(?:a\s+)?(?:call|video)\s+(?:with|to)"
            r"|make\s+(?:a\s+)?call\s+(?:to|with)"
            r"|place\s+(?:a\s+)?call\s+(?:to|with)"
            r"|call|ring|phone|dial"
            r")\s+(.+)",
            utterance, _re.I,
        )

        if m:
            # Strip trailing filler so "call John please" → "John"
            name = _re.sub(
                r"\s+(?:please|now|for me|on teams|via teams|on zoom|thanks|thank you)$",
                "", m.group(1).strip(), flags=_re.I,
            ).strip()
        else:
            # Bare utterance (no "call" keyword) — treat the whole thing as the name
            name = utterance.strip()

        if not name:
            await self._tts.speak("Who would you like to call?", priority="normal")
            name = await self._stt.listen_once()
            if not name:
                await self._tts.speak("Call cancelled.", priority="normal")
                return
            name = name.strip()

        cached = self._lookup_contact_cached(name, count=3)
        if cached is not None and cached:
            results = cached
        else:
            try:
                results = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: self._graph.search_contacts(name, count=3)
                )
            except Exception:
                log.exception("Contact search failed for call")
                await self._tts.speak(
                    "Contact search failed. "
                    "Make sure Microsoft 365 is signed in and Teams is open. "
                    "If this keeps happening, the People permission may not be granted "
                    "in your Azure app registration.",
                    priority="normal",
                )
                return

        if not results:
            await self._tts.speak(f"No contact found for {name}.", priority="normal")
            return

        contact = await self._disambiguate_contact(results)
        if contact is None:
            return

        display_name = contact.get("displayName", name)
        email        = contact.get("emailAddress", "")
        dept         = contact.get("department", contact.get("jobTitle", ""))
        phone_raw    = (contact.get("phone") or "").strip()
        extension    = re.sub(r"\D", "", (contact.get("extension") or "").strip())

        # Normalise phone to digits only, then to E.164 for US numbers
        phone = re.sub(r"[^\d+]", "", phone_raw)
        if phone and not phone.startswith("+"):
            if len(phone) == 10:
                phone = "+1" + phone
            elif len(phone) == 11 and phone.startswith("1"):
                phone = "+" + phone

        # Validate email: the domain must contain at least one letter.
        # Some Azure AD users have numeric SIP/legacy UPNs (e.g. "12345@67890.123")
        # that look like emails but will fail with "Unavailable" in Teams.
        email_valid = bool(
            email and "@" in email
            and re.search(r"[a-zA-Z]", email.split("@")[-1])
        )

        if not email_valid and not phone and not extension:
            await self._tts.speak(
                f"{display_name} has no contact details on file.",
                priority="normal",
            )
            return

        dept_part     = f" from {dept}" if dept else ""
        call_prefix   = "Video calling" if with_video else "Calling"
        connect_label = "video call" if with_video else "call"

        # Step 1: announce immediately — before any network calls
        await self._tts.speak(
            f"{call_prefix} {display_name}{dept_part} — say stop to cancel.",
            priority="normal",
        )

        # Step 2: if audio call and phone missing (and no extension), try Azure AD by UPN.
        # People API often omits businessPhones even when Azure AD has them.
        if not phone and not extension and email and not with_video:
            try:
                phone_ad = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: self._graph.get_user_phone(email)
                )
                if phone_ad:
                    phone = re.sub(r"[^\d+]", "", phone_ad)
                    if phone and not phone.startswith("+"):
                        if len(phone) == 10:
                            phone = "+1" + phone
                        elif len(phone) == 11 and phone.startswith("1"):
                            phone = "+" + phone
            except Exception:
                log.debug("Fallback phone lookup failed for %s", email)

        # Step 3: route
        #   video         → Teams email/UPN (must be valid)
        #   audio + phone → tel: (Win32 native dialog, most reliable)
        #   audio + ext   → callto:ext (Win32 dialog via Teams Skype handler)
        #   audio + email → callto:email (Teams-to-Teams, only if email_valid)
        using_upn = False
        if with_video:
            if email_valid:
                call_target = [email]
                using_upn = True
            else:
                await self._tts.speak("No Teams address found for video call.", priority="normal")
                return
        elif phone:
            call_target = [f"4:{phone}"]
        elif extension:
            call_target = [f"4:{extension}"]
        elif email_valid:
            call_target = [email]
            using_upn = True
        else:
            await self._tts.speak("No phone, extension, or Teams address found.", priority="normal")
            return

        # Step 4: fire URI — os.startfile returns instantly;
        #         dial_teams starts background dialog-confirm thread immediately.
        from core.meeting import controls as _ctrl
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: _ctrl.dial_teams(call_target, with_video=with_video, display_name=display_name)
        )
        if ok:
            if self._meeting_orchestrator:
                self._meeting_orchestrator.in_meeting = True
                self._meeting_orchestrator.current_platform = "teams"
            await self._tts.speak(
                f"Connecting {connect_label} to {display_name}.", priority="normal"
            )
        else:
            await self._tts.speak(
                "Could not start the call. Make sure Teams is open and running.",
                priority="normal",
            )

    async def _action_call_extension(self, utterance: str) -> None:
        """Dial an internal extension number (3–6 digits) via Teams."""
        import re as _re
        m = _re.search(r"(?:extension|ext\.?|x|internal)\s*(\d{3,6})", utterance, _re.I)
        if not m:
            digits = _re.sub(r"\D", "", utterance)
            ext = digits if 3 <= len(digits) <= 6 else None
        else:
            ext = m.group(1)

        if not ext:
            await self._tts.speak(
                "What extension? Say extension followed by the number, for example: extension 1234.",
                priority="normal",
            )
            follow = await self._stt.listen_command()
            if not follow:
                await self._tts.speak("Call cancelled.", priority="normal")
                return
            dm = _re.search(r"\d{3,6}", follow)
            if not dm:
                await self._tts.speak("No extension number heard. Call cancelled.", priority="normal")
                return
            ext = dm.group(0)

        # Step 1: announce immediately
        await self._tts.speak(
            f"Extension {ext}. Calling — say stop to cancel.", priority="normal"
        )

        # Step 2: fire tel:{ext} URI — os.startfile returns instantly;
        #         dial_teams also starts the background dialog-confirm thread immediately.
        from core.meeting import controls as _ctrl
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: _ctrl.dial_teams([f"4:{ext}"])
        )

        if ok:
            # Step 3: confirm immediately — background thread is already polling for "Call"
            if self._meeting_orchestrator:
                self._meeting_orchestrator.in_meeting = True
                self._meeting_orchestrator.current_platform = "teams"
            await self._tts.speak(f"Connecting to extension {ext}.", priority="normal")
        else:
            await self._tts.speak(
                "Could not dial. Make sure Teams is open and running.", priority="normal"
            )

    async def _action_call_number(self, utterance: str) -> None:
        """Dial a full PSTN phone number on Teams."""
        import re as _re
        raw_digits = _re.sub(r"[^\d+]", "", utterance)

        if len(raw_digits) < 7:
            await self._tts.speak(
                "What number? Say dial followed by the digits.", priority="normal"
            )
            follow = await self._stt.listen_command()
            if not follow:
                await self._tts.speak("Call cancelled.", priority="normal")
                return
            raw_digits = _re.sub(r"[^\d+]", "", follow)
            if len(raw_digits) < 7:
                await self._tts.speak("No valid number heard. Call cancelled.", priority="normal")
                return

        # Normalise to E.164 for US/Canada 10-digit numbers
        number = raw_digits
        if not number.startswith("+") and len(number) == 10:
            number = "+1" + number
        elif not number.startswith("+") and len(number) == 11 and number.startswith("1"):
            number = "+" + number

        spoken = " ".join(number)
        await self._tts.speak(f"Dialling {spoken}.", priority="normal")

        from core.meeting import controls as _ctrl
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: _ctrl.dial_teams([f"4:{number}"])
        )
        if ok:
            await asyncio.get_running_loop().run_in_executor(None, _earcon_done)
            if self._meeting_orchestrator:
                self._meeting_orchestrator.in_meeting = True
                self._meeting_orchestrator.current_platform = "teams"
            await self._tts.speak("Connecting.", priority="normal")
        else:
            await asyncio.get_running_loop().run_in_executor(None, _earcon_error)
            await self._tts.speak(
                "Could not dial. Make sure Teams Phone is enabled on your account.",
                priority="normal",
            )

    async def _action_conference_call(self, utterance: str) -> None:
        """Start a Teams conference call with multiple contacts looked up by name."""
        if not self._graph:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return

        import re as _re
        m = _re.search(
            r"(?:(?:conference|group)\s+call(?:\s+with)?"
            r"|start\s+a?\s*conference\s+(?:call\s+)?(?:with)?"
            r"|call\s+everyone\s+(?:including)?)\s+(.+)$",
            utterance, _re.I,
        )
        if not m:
            await self._tts.speak(
                "Who should be on the call? "
                "Say conference call with, then names separated by and.",
                priority="normal",
            )
            return

        raw_names = _re.split(r"\s+and\s+|,\s*", m.group(1).strip())
        names     = [n.strip() for n in raw_names if n.strip()]
        if not names:
            await self._tts.speak("No names heard. Call cancelled.", priority="normal")
            return

        found: list[dict] = []
        not_found: list[str] = []
        for name in names:
            cached = self._lookup_contact_cached(name, count=1)
            if cached is not None:
                if cached and cached[0].get("emailAddress"):
                    found.append(cached[0])
                else:
                    not_found.append(name)
                continue
            try:
                results = await asyncio.get_running_loop().run_in_executor(
                    None, lambda n=name: self._graph.search_contacts(n, count=1)
                )
                if results and results[0].get("emailAddress"):
                    found.append(results[0])
                else:
                    not_found.append(name)
            except Exception:
                log.exception("Contact search failed for %s", name)
                not_found.append(name)

        if not_found:
            await self._tts.speak(
                f"Could not find: {', '.join(not_found)}. Skipping them.", priority="normal"
            )
        if not found:
            await self._tts.speak("No contacts found. Call cancelled.", priority="normal")
            return

        emails       = [c["emailAddress"] for c in found]
        display_list = " and ".join(c["displayName"] for c in found)

        await self._tts.speak(
            f"Starting conference call with {display_list}.", priority="normal"
        )

        from core.meeting import controls as _ctrl
        ok = await asyncio.get_running_loop().run_in_executor(
            None, lambda: _ctrl.dial_teams(emails)
        )
        if ok:
            await asyncio.get_running_loop().run_in_executor(None, _earcon_done)
            if self._meeting_orchestrator:
                self._meeting_orchestrator.in_meeting = True
                self._meeting_orchestrator.current_platform = "teams"
            await self._tts.speak(
                f"Connecting conference call with {display_list}.", priority="normal"
            )
        else:
            await asyncio.get_running_loop().run_in_executor(None, _earcon_error)
            await self._tts.speak(
                "Could not start the conference call. Make sure Teams is open.",
                priority="normal",
            )

    # ── Incoming call watcher ─────────────────────────────────────────

    async def _incoming_call_watcher(self) -> None:
        """
        Poll every INCOMING_CALL_POLL_SECONDS for a ringing Teams/Zoom window.
        When a call is detected, announce it once and route through the consent
        FSM (answer / decline).  After the call is handled or the window
        disappears, remove the key from _announced_calls so a subsequent call
        from the same caller is not silently skipped.
        """
        from core.meeting import controls as _ctrl
        from core.consent.state_machine import ConsentRequest

        while True:
            await asyncio.sleep(INCOMING_CALL_POLL_SECONDS)
            try:
                info = await asyncio.get_running_loop().run_in_executor(
                    None, _ctrl.find_incoming_call_info
                )
                if not info:
                    # No active ring — clear stale keys
                    self._announced_calls.clear()
                    continue

                caller, platform = info
                call_key = f"{caller}_{platform}"
                if call_key in self._announced_calls:
                    continue  # already routed this ring

                self._announced_calls.add(call_key)
                platform_name = platform.title()

                async def answer(p=platform) -> None:
                    loop = asyncio.get_running_loop()
                    ok = await loop.run_in_executor(
                        None, lambda: _ctrl.answer_call(p, with_video=False)
                    )
                    if ok:
                        if self._meeting_orchestrator:
                            self._meeting_orchestrator.in_meeting = True
                            self._meeting_orchestrator.current_platform = p
                        await self._tts.speak("Call answered.", priority="normal")
                    else:
                        await self._tts.speak(
                            "Could not answer the call automatically. "
                            "The call window may have closed.",
                            priority="normal",
                        )

                answered = await self._fsm.request(ConsentRequest(
                    notification=f"Incoming {platform_name} call from {caller}.",
                    query="Should I answer?",
                    action=answer,
                    action_label=f"answer_call_{platform}_{caller[:20]}",
                ))

                if not answered:
                    # Record as a missed call so "what did I miss" can report it
                    self._missed_calls.append({
                        "caller":   caller,
                        "platform": platform_name,
                        "time":     datetime.now(),
                    })
                    # Decline the ring so Teams stops ringing
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda p=platform: _ctrl.decline_call(p)
                    )

            except Exception:
                log.exception("Incoming call watcher error")

    # ── Compose new email ─────────────────────────────────────────────

    async def _action_compose_email(self, utterance: str) -> None:
        if not self._email_suite:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return
        await self._email_suite.compose_wizard()

    # ── Calendar by day ───────────────────────────────────────────────

    async def _action_calendar_for_day(self, utterance: str) -> None:
        if not self._meeting_orchestrator:
            await self._tts.speak("Calendar is not connected.", priority="normal")
            return

        text = utterance.lower()
        now  = datetime.now()

        if "tomorrow" in text:
            target = now + timedelta(days=1)
            label  = "tomorrow"
        elif "today" in text or "calendar" in text:
            target = now
            label  = "today"
        else:
            target = now
            label  = "today"
            for day_name, day_num in _DAY_NAMES.items():
                if day_name in text:
                    days_ahead = (day_num - now.weekday()) % 7 or 7
                    target = now + timedelta(days=days_ahead)
                    label  = day_name.capitalize()
                    break

        events = []
        for src in self._meeting_orchestrator._sources:
            fn = getattr(src, "events_for_day", None)
            if fn:
                try:
                    evts = await asyncio.get_running_loop().run_in_executor(
                        None, lambda s=src: s.events_for_day(target)
                    )
                    events.extend(evts)
                except Exception:
                    log.exception("Failed to fetch events for %s", label)

        events.sort(key=lambda e: e.start)

        if not events:
            await self._tts.speak(
                f"No meetings scheduled for {label}.", priority="normal"
            )
            return

        count = len(events)
        await self._tts.speak(
            f"You have {count} meeting{'s' if count != 1 else ''} on {label}.",
            priority="normal",
        )
        for event in events:
            local_start  = event.start.astimezone()
            time_str     = local_start.strftime("%I:%M %p").lstrip("0")
            platform_name = (event.platform or "meeting").replace("_", " ").title()
            role = "host" if event.is_organizer else "participant"
            await self._tts.speak(
                f"{time_str}: {event.subject}. {platform_name}. You are the {role}.",
                priority="normal",
            )

    # ── "What did I miss?" ────────────────────────────────────────────

    async def _action_what_did_i_miss(self) -> None:
        if not self._email_suite:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return

        # Fetch upcoming meetings from all sources in parallel
        upcoming: list = []
        if self._meeting_orchestrator and self._meeting_orchestrator._sources:
            now = datetime.now(timezone.utc)
            loop = asyncio.get_running_loop()
            src_tasks = [
                loop.run_in_executor(None, lambda s=src: s.upcoming_events(5))
                for src in self._meeting_orchestrator._sources
            ]
            src_results = await asyncio.gather(*src_tasks, return_exceptions=True)
            for result in src_results:
                if isinstance(result, Exception):
                    log.warning("Could not fetch upcoming events: %s", result)
                else:
                    upcoming.extend(
                        e for e in result
                        if 0 <= (e.start - now).total_seconds() <= 3600
                    )
            upcoming.sort(key=lambda e: e.start)

        # Build missed-call summary from this session
        missed_calls_part = self._build_missed_calls_summary()

        await self._email_suite.what_did_i_miss(
            upcoming_meetings=upcoming or None,
            missed_calls_summary=missed_calls_part,
        )

    def _build_missed_calls_summary(self) -> str:
        """Return a spoken sentence describing missed Teams calls this session."""
        if not self._missed_calls:
            return ""
        # Purge calls older than 8 hours so stale entries don't linger across long sessions
        cutoff = datetime.now().timestamp() - 8 * 3600
        self._missed_calls = [
            c for c in self._missed_calls
            if c["time"].timestamp() >= cutoff
        ]
        if not self._missed_calls:
            return ""

        count = len(self._missed_calls)
        if count == 1:
            c = self._missed_calls[0]
            t = c["time"].strftime("%I:%M %p").lstrip("0")
            return f"1 missed {c['platform']} call from {c['caller']} at {t}."
        # Multiple — list up to 3 callers, then a count for the rest
        parts = []
        for c in self._missed_calls[-3:]:          # most recent 3
            t = c["time"].strftime("%I:%M %p").lstrip("0")
            parts.append(f"{c['caller']} at {t}")
        callers = ", ".join(parts)
        return f"{count} missed Teams calls: {callers}."

    # ── Reminder ──────────────────────────────────────────────────────

    async def _action_set_reminder(self, utterance: str) -> None:
        feedback = self._reminder_engine.schedule(utterance)
        await self._tts.speak(feedback, priority="normal")

    # ── Speed control ─────────────────────────────────────────────────

    async def _action_speed_up(self) -> None:
        new_rate = self._tts.set_rate(+2)
        label = "faster" if new_rate > -1 else "normal"
        await self._tts.speak(f"Speaking {label}.", priority="normal")

    async def _action_speed_down(self) -> None:
        new_rate = self._tts.set_rate(-2)
        label = "slower" if new_rate < -1 else "normal"
        await self._tts.speak(f"Speaking {label}.", priority="normal")

    async def _action_speed_normal(self) -> None:
        # Reset to default by shifting back to -1
        current = self._tts.get_rate()
        self._tts.set_rate(-1 - current)
        await self._tts.speak("Speaking at normal speed.", priority="normal")

    # ── Repeat last ───────────────────────────────────────────────────

    async def _action_repeat(self) -> None:
        last = self._tts.repeat_last()
        if last:
            await self._tts.speak(last, priority="normal")
        else:
            await self._tts.speak("Nothing to repeat yet.", priority="normal")

    # ── System info ───────────────────────────────────────────────────

    async def _action_time(self) -> None:
        t = await asyncio.get_running_loop().run_in_executor(None, sys_status.get_time_spoken)
        await self._tts.speak(f"The time is {t}.", priority="normal")

    async def _action_date(self) -> None:
        d = await asyncio.get_running_loop().run_in_executor(None, sys_status.get_date_spoken)
        await self._tts.speak(f"Today is {d}.", priority="normal")

    async def _action_battery(self) -> None:
        b = await asyncio.get_running_loop().run_in_executor(None, sys_status.get_battery_status)
        await self._tts.speak(b, priority="normal")

    async def _action_where_am_i(self) -> None:
        info = await asyncio.get_running_loop().run_in_executor(
            None, sys_status.get_foreground_window_info
        )
        await self._tts.speak(info, priority="normal")

    async def _action_recent_files(self) -> None:
        files = await asyncio.get_running_loop().run_in_executor(
            None, lambda: sys_status.get_recent_files(5)
        )
        if not files:
            await self._tts.speak("No recent files found.", priority="normal")
            return
        count = len(files)
        await self._tts.speak(
            f"{count} recent file{'s' if count != 1 else ''}. "
            + ". ".join(files) + ".",
            priority="normal",
        )

    async def _action_read_clipboard(self) -> None:
        text = await asyncio.get_running_loop().run_in_executor(None, sys_status.read_clipboard)
        if not text:
            await self._tts.speak("The clipboard is empty.", priority="normal")
            return
        word_count = len(text.split())
        await self._tts.speak(
            f"Clipboard contains {word_count} word{'s' if word_count != 1 else ''}. {text}",
            priority="normal",
        )

    async def _action_phonetic_spell(self, utterance: str) -> None:
        # Extract what to spell: "spell [word]" or "spell that"
        import re as _re
        m = _re.search(r"\bspell\s+(that|.+)$", utterance, _re.I)
        if not m or m.group(1).lower() == "that":
            last = self._tts.repeat_last()
            words = last.split()
            import string as _str
            target = words[-1].strip(_str.punctuation) if words else ""
        else:
            target = m.group(1).strip()
        if not target:
            await self._tts.speak("Nothing to spell.", priority="normal")
            return
        spelled = sys_status.phonetic_spell(target)
        await self._tts.speak(f"Spelling {target}: {spelled}", priority="normal")

    # ── Weather ───────────────────────────────────────────────────────

    async def _action_weather(self) -> None:
        await self._tts.speak("Fetching weather. One moment.", priority="normal")
        spoken = await asyncio.get_running_loop().run_in_executor(
            None, self._weather_service.get_weather_spoken
        )
        await self._tts.speak(spoken, priority="normal")

    # ── To Do ─────────────────────────────────────────────────────────

    async def _action_tasks(self) -> None:
        if not self._todo_engine:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return
        await self._todo_engine.announce_tasks()

    async def _action_add_task(self, utterance: str) -> None:
        if not self._todo_engine:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return
        import re as _re
        m = _re.search(
            r"(?:add\s+a?\s*task|new\s+task|create\s+a?\s*task|add\s+to\s*do)\s+(.+)$",
            utterance, _re.I,
        )
        if m:
            title = m.group(1).strip()
        else:
            await self._tts.speak(
                "What is the task? Say the title after the beep.", priority="normal"
            )
            follow = await self._stt.listen_once()
            if not follow:
                await self._tts.speak("No task heard. Cancelled.", priority="normal")
                return
            title = follow.strip()
        ok = await self._todo_engine.add_task(title)
        if ok:
            await self._tts.speak(f"Task added: {title}.", priority="normal")
        else:
            await self._tts.speak("Could not add the task. Please try again.", priority="normal")

    async def _action_complete_task(self, utterance: str) -> None:
        if not self._todo_engine:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return
        import re as _re
        m = _re.search(
            r"(?:complete(?:\s+task)?|mark\s+(?:as\s+)?(?:done|complete)"
            r"|finish(?:\s+task)?|done\s+with|mark\s+task)\s+(.+)$",
            utterance, _re.I,
        )
        fragment = m.group(1).strip() if m else utterance
        title = await self._todo_engine.complete_task(fragment)
        if title:
            await self._tts.speak(f"Marked done: {title}.", priority="normal")
        else:
            await self._tts.speak(
                f"No task matching '{fragment}' found.", priority="normal"
            )

    # ── Contacts ──────────────────────────────────────────────────────

    async def _action_find_contact(self, utterance: str) -> None:
        if not self._email_suite:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")
            return
        import re as _re
        m = _re.search(r"(?:who is|find contact|contact|look up)\s+(.+)$", utterance, _re.I)
        query = m.group(1).strip() if m else utterance
        await self._email_suite.search_contacts(query)

    # ── Teams status ──────────────────────────────────────────────────

    async def _action_set_status(self, utterance: str) -> None:
        text = utterance.lower()
        if any(w in text for w in ("busy",)):
            availability, activity = "Busy", "Busy"
            label = "busy"
        elif any(w in text for w in ("do not disturb", "dnd", "focus")):
            availability, activity = "DoNotDisturb", "DoNotDisturb"
            label = "do not disturb"
        elif any(w in text for w in ("away", "be right back", "brb")):
            availability, activity = "Away", "Away"
            label = "away"
        else:
            availability, activity = "Available", "Available"
            label = "available"

        if self._meeting_orchestrator:
            for src in self._meeting_orchestrator._sources:
                if hasattr(src, "set_presence"):
                    try:
                        await asyncio.get_running_loop().run_in_executor(
                            None, lambda s=src: s.set_presence(availability, activity)
                        )
                    except Exception:
                        log.exception("Failed to set presence")
            await self._tts.speak(f"Status set to {label}.", priority="normal")
        else:
            await self._tts.speak("Microsoft 365 is not connected.", priority="normal")

    # ── Quiet hours ───────────────────────────────────────────────────

    async def _action_quiet_hours(self, utterance: str) -> None:
        import re as _re
        m = _re.search(r"(\d+)\s*minute", utterance, _re.I)
        if m:
            minutes = int(m.group(1))
        else:
            m = _re.search(r"(\d+)\s*hour", utterance, _re.I)
            minutes = int(m.group(1)) * 60 if m else 30

        if self._email_suite:
            self._email_suite.set_quiet_hours(minutes)
        spoken_time = f"{minutes} minute{'s' if minutes != 1 else ''}"
        if minutes >= 60:
            h, rem = divmod(minutes, 60)
            spoken_time = f"{h} hour{'s' if h != 1 else ''}"
            if rem:
                spoken_time += f" and {rem} minute{'s' if rem != 1 else ''}"
        await self._tts.speak(
            f"Quiet mode on for {spoken_time}. I will not announce new messages.",
            priority="normal",
        )

    # ── Verbosity ─────────────────────────────────────────────────────

    async def _action_set_verbosity(self, utterance: str) -> None:
        text = utterance.lower()
        if any(w in text for w in ("terse", "brief", "short", "less")):
            if self._email_suite:
                self._email_suite.verbosity = "terse"
            await self._tts.speak("Terse mode on. Shorter announcements.", priority="normal")
        else:
            if self._email_suite:
                self._email_suite.verbosity = "normal"
            await self._tts.speak("Verbose mode on. Full announcements.", priority="normal")

    # ------------------------------------------------------------------
    # Central command dispatcher
    # ------------------------------------------------------------------

    async def _dispatch_command(self, utterance: str) -> None:
        text = utterance.lower().strip()
        log.info("Voice command: %r", text)
        # Earcon: command received and routing
        await asyncio.get_running_loop().run_in_executor(None, _earcon_executing)

        # ── System info ───────────────────────────────────────────────
        if any(w in text for w in ("what time", "time is it", "current time")):
            await self._action_time()

        elif any(w in text for w in ("what day", "today's date", "what's the date", "date is it")):
            await self._action_date()

        elif any(w in text for w in ("battery", "power level", "charge")):
            await self._action_battery()

        elif any(w in text for w in ("where am i", "what app", "active window", "what's open")):
            await self._action_where_am_i()

        elif any(w in text for w in ("recent files", "recent documents", "last files")):
            await self._action_recent_files()

        elif any(w in text for w in ("read clipboard", "clipboard", "paste that", "what's copied")):
            await self._action_read_clipboard()

        elif "spell" in text:
            await self._action_phonetic_spell(utterance)

        # ── Weather ───────────────────────────────────────────────────
        elif any(w in text for w in ("weather", "temperature", "forecast", "rain", "sunny")):
            await self._action_weather()

        # ── Email ─────────────────────────────────────────────────────
        # "compose" checked first so "compose email" never falls into inbox
        elif any(w in text for w in ("compose email", "new email", "send email", "write email",
                                      "compose a", "send a message")):
            await self._action_compose_email(utterance)

        elif any(w in text for w in ("inbox", "my email", "read email", "check email",
                                      "any email", "new message")):
            await self._action_inbox()

        # ── Teams chat ────────────────────────────────────────────────
        elif any(w in text for w in ("teams message", "teams chat", "chat message",
                                      "my messages", "unread message")):
            if self._email_suite:
                await self._email_suite.announce_chats()
            else:
                await self._tts.speak("Microsoft 365 is not connected.", priority="normal")

        # ── What did I miss — checked before calendar so "what did I miss today" routes here
        elif any(w in text for w in ("what did i miss", "catch me up", "briefing",
                                      "what have i missed")):
            await self._action_what_did_i_miss()

        # ── Calendar by day — checked BEFORE "next meeting" so "meetings today" routes here
        elif any(w in text for w in (
            "today", "tomorrow", "what's on", "whats on",
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        )):
            await self._action_calendar_for_day(text)

        # ── Calendar — next meeting ────────────────────────────────────
        elif any(w in text for w in ("next meeting", "my meeting", "meeting", "calendar",
                                      "schedule", "upcoming")):
            await self._action_meetings()

        # ── Reminders ─────────────────────────────────────────────────
        elif "remind" in text:
            await self._action_set_reminder(utterance)

        # ── To Do — read list ──────────────────────────────────────────
        elif any(w in text for w in ("my tasks", "my to do", "to do list", "todo", "task list",
                                      "read tasks", "show tasks", "list tasks")):
            await self._action_tasks()

        # ── To Do — add ───────────────────────────────────────────────
        elif any(w in text for w in ("add task", "new task", "add a task", "create task",
                                      "create a task", "add to do")):
            await self._action_add_task(utterance)

        # ── To Do — complete ──────────────────────────────────────────
        elif any(w in text for w in ("complete task", "complete the task", "mark done",
                                      "mark task", "finish task", "done with", "mark as done",
                                      "mark as complete")):
            await self._action_complete_task(utterance)

        # ── Notes ─────────────────────────────────────────────────────
        elif any(w in text for w in (
            "create note", "new note", "dictate note", "add note", "write note", "take note",
        )):
            if self._email_suite:
                await self._email_suite.create_note()
            else:
                await self._tts.speak("Microsoft 365 is not connected.", priority="normal")

        # ── Contacts ──────────────────────────────────────────────────
        elif any(w in text for w in ("who is", "find contact", "look up", "search contact")):
            await self._action_find_contact(utterance)

        # ── Teams status ──────────────────────────────────────────────
        elif any(w in text for w in ("set status", "set my status", "status busy",
                                      "status available", "do not disturb", "set presence",
                                      "change status", "i'm busy", "i'm available",
                                      "i am busy", "i am available")):
            await self._action_set_status(utterance)

        # ── Quiet hours ───────────────────────────────────────────────
        elif any(w in text for w in ("quiet for", "quiet mode", "quiet hours",
                                      "silence notifications", "pause notifications")):
            await self._action_quiet_hours(utterance)

        # ── Verbosity ─────────────────────────────────────────────────
        elif any(w in text for w in ("terse mode", "brief mode", "verbose mode",
                                      "use terse", "use verbose", "short announcements")):
            await self._action_set_verbosity(utterance)

        # ── Meeting controls ──────────────────────────────────────────
        elif any(w in text for w in ("mute me", "mute", "unmute", "toggle mute", "microphone")):
            await self._action_mute_toggle()

        elif any(w in text for w in ("leave meeting", "end meeting", "hang up", "leave call",
                                      "exit meeting", "leave the meeting", "end the meeting")):
            await self._action_leave_meeting()

        elif any(w in text for w in ("raise hand", "raise my hand", "hand up")):
            await self._action_raise_hand()

        elif any(w in text for w in ("camera", "toggle camera", "turn on video", "turn off video", "video on", "video off")):
            await self._action_camera_toggle()

        # ── Outgoing Teams calls — delegate to shared router ─────────────
        elif any(w in text for w in ("conference call", "group call", "call conference",
                                      "call everyone", "start a conference",
                                      "video call", "video chat", "start video",
                                      "start a video", "video with",
                                      "extension", "ext ", "ext.", "dial ext",
                                      "call extension", "internal extension",
                                      "dial", "phone number", "call the number",
                                      "ring", "start a call", "make a call",
                                      "teams call", "place a call", "audio call")) or (
            "call" in text
            and not any(w in text for w in ("leave", "end", "hang", "incoming",
                                             "decline", "conference", "video",
                                             "missed call", "no call"))
        ):
            await self._route_call_utterance(utterance)

        # ── TTS control ───────────────────────────────────────────────
        elif any(w in text for w in ("faster", "speak faster", "speed up", "too slow")):
            await self._action_speed_up()

        elif any(w in text for w in ("slower", "speak slower", "slow down", "too fast")):
            await self._action_speed_down()

        elif any(w in text for w in ("normal speed", "reset speed", "regular speed")):
            await self._action_speed_normal()

        elif any(w in text for w in ("repeat", "repeat that", "say that again", "say again")):
            await self._action_repeat()

        # ── Help ──────────────────────────────────────────────────────
        elif any(w in text for w in ("help", "commands", "what can you do")):
            await self._tts.speak(
                "Here are all available voice commands. "
                # System info
                "What time is it. "
                "What's today's date. "
                "Battery. "
                "Where am I. "
                "Recent files. "
                "Read clipboard. "
                "Spell, followed by a word. "
                "Weather. "
                # Email
                "Inbox — reads unread emails. Say next, read full, reply, or stop while navigating. "
                "Compose email — guided wizard: you will be asked who, subject, then message. After dictating, say send, save draft, re-dictate to redo the message, or cancel. "
                "Teams messages — reads recent Teams chat messages. "
                # Calendar
                "Next meeting. "
                "Today — full schedule for today. "
                "Tomorrow — full schedule for tomorrow. "
                "You can also say any day name, for example: Friday. "
                # Briefing
                "What did I miss — summary of missed calls, recent emails, and upcoming meetings. "
                # Calls
                "Call followed by a name — audio call via Teams. "
                "Video call followed by a name — video call via Teams. "
                "Extension followed by the number — internal extension dial. "
                "Dial followed by a phone number — PSTN call via Teams. "
                "Conference call with names separated by and — group call on Teams. "
                # Reminders
                "Remind me in 5 minutes about the call. "
                # To Do
                "My tasks — reads your Microsoft To Do list. "
                "Add task followed by the title. "
                "Complete task followed by the task name. "
                # Notes
                "Create note — dictate a note saved to OneNote. "
                # Contacts
                "Who is followed by a name — contact lookup. "
                # Teams status
                "Set status busy. Set status available. Set status do not disturb. "
                # Quiet hours
                "Quiet for 30 minutes — pauses all notifications. "
                # Verbosity
                "Terse mode — shorter announcements. Verbose mode — full detail. "
                # TTS speed
                "Faster. Slower. Normal speed. "
                "Repeat that — repeats the last thing I said. "
                # Meeting controls
                "During a meeting: mute me, leave meeting, raise hand, camera. "
                # App control
                "Test — checks that my voice is working. "
                "Quit — closes Lightworks Pro. "
                # Hotkeys
                "Hotkeys: "
                "Control Shift F1 — listen. "
                "Control Shift F2 — inbox. "
                "Control Shift F3 — next meeting. "
                "Control Shift F4 — Teams call. "
                "Control Shift F5 — quit. "
                "Pressing Control Shift F1 while I am speaking stops me immediately.",
                priority="normal",
            )

        # ── Test ──────────────────────────────────────────────────────
        elif any(w in text for w in ("test", "testing")):
            await self._action_test_voice()

        # ── Quit ──────────────────────────────────────────────────────
        elif any(w in text for w in ("stop", "quit", "exit", "close", "goodbye")):
            await self._tts.speak("Goodbye.", priority="alert")
            self._on_quit()

        else:
            await self._tts.speak(
                f"I heard: {utterance}. "
                "I didn't recognise that command. "
                "Say help to hear all commands.",
                priority="normal",
            )

    # ------------------------------------------------------------------
    # Tray icon
    # ------------------------------------------------------------------

    def _build_tray_icon(self) -> pystray.Icon:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=(0, 85, 184))
        d.ellipse((22, 22, 42, 42), fill=(255, 255, 255))

        svc = self

        def _run(coro):
            if svc._loop and svc._loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, svc._loop)

        menu = pystray.Menu(
            pystray.MenuItem("Lightworks Pro", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Listen  [Ctrl+Shift+F1]",
                lambda icon, item: _run(svc._action_listen()),
            ),
            pystray.MenuItem(
                "Read Inbox  [Ctrl+Shift+F2]",
                lambda icon, item: _run(svc._action_inbox()),
            ),
            pystray.MenuItem(
                "Next Meeting  [Ctrl+Shift+F3]",
                lambda icon, item: _run(svc._action_meetings()),
            ),
            pystray.MenuItem(
                "Teams Call  [Ctrl+Shift+F4]",
                lambda icon, item: _run(svc._action_teams_call()),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "What Did I Miss",
                lambda icon, item: _run(svc._action_what_did_i_miss()),
            ),
            pystray.MenuItem(
                "Teams Messages",
                lambda icon, item: _run(
                    svc._email_suite.announce_chats()
                    if svc._email_suite else
                    svc._tts.speak("Microsoft 365 is not connected.", priority="normal")
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Test Voice",
                lambda icon, item: _run(svc._action_test_voice()),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Quit  [Ctrl+Shift+F5]",
                lambda icon, item: svc._on_quit(),
            ),
        )

        return pystray.Icon(
            "LightworksPro", img, "Lightworks Pro — Voice Assistant", menu
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_quit(self) -> None:
        log.info("Shutting down")
        if self._icon:
            self._icon.stop()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
