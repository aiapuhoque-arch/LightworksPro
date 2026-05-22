"""
Consent FSM — enforces Notification → Query → Consent → Execution for every action.
No action is ever taken without an explicit affirmative from the user.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Awaitable, Callable, Optional

log = logging.getLogger(__name__)


class ConsentState(Enum):
    IDLE = auto()
    NOTIFICATION = auto()   # Speaking the alert to the user
    QUERY = auto()          # Asking "Should I do X?"
    LISTENING = auto()      # Waiting for voice response
    CONFIRMED = auto()      # Affirmative received
    REJECTED = auto()       # Negative received or timeout
    EXECUTING = auto()      # Carrying out the consented action
    COMPLETED = auto()      # Action finished, returning to IDLE


AFFIRMATIVES = frozenset({"yes", "yeah", "yep", "ok", "okay", "sure", "do it",
                           "join", "send", "start", "go", "confirm", "proceed",
                           "please", "of course", "absolutely", "definitely",
                           "answer", "accept", "open"})
NEGATIVES = frozenset({"no", "nope", "cancel", "stop", "don't", "skip", "abort",
                        "not now", "later", "dismiss"})

LISTEN_TIMEOUT_SECONDS = 12


@dataclass
class ConsentRequest:
    """Describes a single action pending user consent."""
    notification: str          # "You have a Teams meeting starting in 2 minutes."
    query: str                 # "Should I join as a participant?"
    action: Callable[[], Awaitable[None]]
    action_label: str          # Short label for logging, e.g. "join_teams_meeting"
    timeout: float = LISTEN_TIMEOUT_SECONDS


class ConsentFSM:
    """
    Single-request serialised consent gate.

    Usage:
        fsm = ConsentFSM(tts=tts_engine, stt=stt_engine)
        await fsm.request(ConsentRequest(...))
    """

    def __init__(self, tts, stt) -> None:
        self._tts = tts
        self._stt = stt
        self._state = ConsentState.IDLE
        self._lock = asyncio.Lock()
        self._current: Optional[ConsentRequest] = None

    @property
    def state(self) -> ConsentState:
        return self._state

    async def request(self, req: ConsentRequest) -> bool:
        """
        Run the full Notification → Query → Consent → Execution loop.
        Returns True if the action was executed, False if rejected or timed out.
        Only one consent request runs at a time; concurrent callers queue behind the lock.
        """
        async with self._lock:
            self._current = req
            return await self._run(req)

    async def _run(self, req: ConsentRequest) -> bool:
        try:
            await self._notify(req)
            confirmed = await self._query(req)
            if confirmed:
                await self._execute(req)
            return confirmed
        except asyncio.CancelledError:
            self._state = ConsentState.IDLE
            raise
        finally:
            self._current = None
            self._state = ConsentState.IDLE

    async def _notify(self, req: ConsentRequest) -> None:
        self._state = ConsentState.NOTIFICATION
        log.info("NOTIFY [%s]: %s", req.action_label, req.notification)
        await self._tts.speak(req.notification, priority="alert")

    async def _query(self, req: ConsentRequest) -> bool:
        self._state = ConsentState.QUERY
        await self._tts.speak(req.query, priority="alert")

        # Brief pause so TTS audio fully clears the microphone before recording starts.
        await asyncio.sleep(0.4)

        self._state = ConsentState.LISTENING
        try:
            utterance = await asyncio.wait_for(
                self._stt.listen_once(), timeout=req.timeout
            )
        except asyncio.TimeoutError:
            log.info("CONSENT TIMEOUT [%s] — treating as rejection", req.action_label)
            await self._tts.speak("No response received. Skipping.", priority="alert")
            self._state = ConsentState.REJECTED
            return False

        if not utterance:
            self._state = ConsentState.REJECTED
            return False

        normalised = utterance.strip().lower()
        log.info("HEARD [%s]: %r", req.action_label, normalised)

        if any(word in normalised for word in AFFIRMATIVES):
            self._state = ConsentState.CONFIRMED
            return True

        self._state = ConsentState.REJECTED
        await self._tts.speak("Understood. Skipping.", priority="alert")
        return False

    async def _execute(self, req: ConsentRequest) -> None:
        self._state = ConsentState.EXECUTING
        log.info("EXECUTING [%s]", req.action_label)
        await req.action()
        self._state = ConsentState.COMPLETED
        log.info("COMPLETED [%s]", req.action_label)
