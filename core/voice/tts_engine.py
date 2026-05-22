"""
System TTS dispatcher — routes speech through OS SAPI5 (Windows).

New in this version:
  interrupt()   — stop current utterance and drain queue immediately
  set_rate(d)   — shift speaking rate by d steps (-5..5); next utterance picks it up
  get_rate()    — return current rate
  repeat_last() — return the text of the most recently spoken item

Threading model:
  - SpVoice is created INSIDE the worker thread (COM STA requirement).
  - Speak is issued with SVSFlagsAsync so the worker can poll for interruption
    every POLL_MS milliseconds without blocking the whole thread on a long sentence.
  - Callers await speak() from any asyncio coroutine; the asyncio.Event is set
    by call_soon_threadsafe once SAPI signals completion (or purge on interrupt).
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

Priority = Literal["alert", "normal"]

# SAPI5 SpeakFlags
_SVSFlagsAsync        = 1
_SVSFPurgeBeforeSpeak = 2

_SAPI_RATE   = -1    # -10..10; -1 ≈ comfortable reading pace
_SAPI_VOLUME = 100
_POLL_MS     = 50    # interrupt-check interval (ms) inside the worker


@dataclass
class _SpeechItem:
    seq:  int
    text: str
    loop: asyncio.AbstractEventLoop
    done: asyncio.Event

    def __lt__(self, other: "_SpeechItem") -> bool:
        return self.seq < other.seq

    def __le__(self, other: "_SpeechItem") -> bool:
        return self.seq <= other.seq


class TTSEngine:
    """
    Thread-safe TTS dispatcher backed by SAPI5 via win32com.

    Priority "alert" items jump ahead of queued "normal" items.
    Within the same priority, FIFO order is preserved via a sequence counter.
    """

    def __init__(self) -> None:
        self._q: queue.PriorityQueue[tuple[int, int, _SpeechItem]] = queue.PriorityQueue()
        self._seq   = itertools.count()
        self._interrupted = threading.Event()
        self._last_text: str = ""
        self._rate = _SAPI_RATE
        self._rate_lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True, name="lw-tts")
        self._worker.start()

    # ------------------------------------------------------------------
    # Public API — called from async code
    # ------------------------------------------------------------------

    async def speak(self, text: str, *, priority: Priority = "normal") -> None:
        """Enqueue text and suspend until it has been spoken (or interrupted)."""
        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        order = 0 if priority == "alert" else 1
        item = _SpeechItem(seq=next(self._seq), text=text, loop=loop, done=done)
        self._q.put((order, item.seq, item))
        await done.wait()

    def interrupt(self) -> None:
        """
        Stop the current utterance immediately and discard all queued items.
        Each discarded item's done-event is signalled so any awaiting coroutine
        unblocks rather than hanging.
        """
        self._interrupted.set()
        # Drain the queue, releasing every waiting coroutine
        while True:
            try:
                _, _, item = self._q.get_nowait()
                item.loop.call_soon_threadsafe(item.done.set)
            except queue.Empty:
                break

    def repeat_last(self) -> str:
        """Return the text of the most recently spoken item."""
        return self._last_text

    def set_rate(self, delta: int) -> int:
        """
        Shift the speech rate by delta steps (positive = faster).
        Clamped to -5..5. Returns the new rate value.
        The change takes effect on the next queued utterance.
        """
        with self._rate_lock:
            self._rate = max(-5, min(5, self._rate + delta))
            return self._rate

    def get_rate(self) -> int:
        with self._rate_lock:
            return self._rate

    # ------------------------------------------------------------------
    # Worker — runs on dedicated COM STA thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Volume = _SAPI_VOLUME
            while True:
                _, _, item = self._q.get()
                self._last_text = item.text
                self._interrupted.clear()
                try:
                    with self._rate_lock:
                        voice.Rate = self._rate
                    log.debug("TTS: %r", item.text)
                    # Async speak — lets us poll for interruption
                    voice.Speak(item.text, _SVSFlagsAsync)
                    while not voice.WaitUntilDone(_POLL_MS):
                        if self._interrupted.is_set():
                            # Purge current speech immediately
                            voice.Speak("", _SVSFPurgeBeforeSpeak | _SVSFlagsAsync)
                            voice.WaitUntilDone(200)   # wait for purge to settle
                            break
                except Exception:
                    log.exception("TTS worker error")
                finally:
                    item.loop.call_soon_threadsafe(item.done.set)
        finally:
            pythoncom.CoUninitialize()
