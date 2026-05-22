"""
STT Engine — on-device speech recognition for Windows.

Recording uses sounddevice (no PyAudio needed). Audio is captured as a
numpy array and converted to sr.AudioData for transcription.

Primary:  OpenAI Whisper (local, offline) — when openai-whisper is installed.
Fallback: SpeechRecognition + Google Web Speech API (internet required).

Two listen modes:
  listen_once()    — full utterance mode for dictation (up to 15 s, 1.6 s silence)
  listen_command() — short command mode for navigation ("next", "stop") — no
                     asyncio.wait_for timeout needed because the recording
                     naturally finishes within ~4 s, avoiding the executor-
                     cancellation race that broke inbox navigation.
"""
from __future__ import annotations

import asyncio
import io
import logging
import threading
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000   # Hz — required by Google STT and Whisper
CHUNK_SECS  = 0.2      # seconds per VAD chunk

# Dictation mode
DICTATION_SILENCE_CHUNKS = 8     # 8 × 0.2 s = 1.6 s silence → end of utterance
DICTATION_MAX_SECS       = 15.0
DICTATION_WARMUP_SECS    = 0.4

# Command mode — optimised for short words ("next", "stop", "yes", "no")
COMMAND_SILENCE_CHUNKS   = 3     # 3 × 0.2 s = 0.6 s silence → done
COMMAND_MAX_SECS         = 4.0   # never wait more than 4 s
COMMAND_WARMUP_SECS      = 0.15  # brief calibration

# Noise floor seed; kept persistent across calls as a rolling estimate.
# 0.008 is conservative — most quiet rooms are well below this; speech is ~10×.
_SILENCE_RMS_SEED = 0.008


class STTEngine:
    """
    Records one utterance from the default microphone and returns a transcription.

    Usage (async):
        stt = STTEngine()
        text = await stt.listen_once()    # full dictation
        text = await stt.listen_command() # short navigation command
    """

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._whisper = None
        self._preload_started = False
        # One lock so two listen calls never overlap on the same device.
        self._lock = asyncio.Lock()
        # Persistent noise floor — updated after each successful recording.
        self._noise_floor: float = _SILENCE_RMS_SEED

    def preload(self) -> None:
        """Load the Whisper model in a daemon thread at startup (fire-and-forget).
        Safe to call multiple times — only the first call starts the thread.
        """
        if self._preload_started:
            return
        self._preload_started = True
        threading.Thread(
            target=self._ensure_whisper, daemon=True, name="whisper-preload"
        ).start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def listen_once(self, max_secs: float = DICTATION_MAX_SECS) -> str:
        """Full utterance capture for dictation and main commands.

        max_secs — maximum seconds to wait for speech to begin (default 15).
        Once speech is detected the recording ends naturally after 1.6 s silence.
        """
        _play_ready_beep()
        # Wait for the beep's room echo to fully decay before opening the mic.
        await asyncio.sleep(0.45)
        async with self._lock:
            return await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._record_and_transcribe(
                    silence_chunks=DICTATION_SILENCE_CHUNKS,
                    max_secs=max_secs,
                    warmup_secs=DICTATION_WARMUP_SECS,
                ),
            )

    async def listen_command(self) -> str:
        """
        Short command capture for navigation words like 'next' and 'stop'.
        Uses tighter VAD settings so it finishes naturally without needing
        asyncio.wait_for (which would orphan the recording thread).
        Plays a soft ready-beep before opening the microphone.
        """
        _play_ready_beep()
        await asyncio.sleep(0.2)
        async with self._lock:
            return await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._record_and_transcribe(
                    silence_chunks=COMMAND_SILENCE_CHUNKS,
                    max_secs=COMMAND_MAX_SECS,
                    warmup_secs=COMMAND_WARMUP_SECS,
                ),
            )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _record_and_transcribe(
        self,
        *,
        silence_chunks: int,
        max_secs: float,
        warmup_secs: float,
    ) -> str:
        audio = self._record_via_sounddevice(
            silence_chunks=silence_chunks,
            max_secs=max_secs,
            warmup_secs=warmup_secs,
        )
        if audio is None or len(audio) == 0:
            return ""
        # Normalise amplitude so quiet speech reaches Whisper's optimal range
        peak = float(np.abs(audio).max())
        if peak > 0:
            audio = audio * (0.9 / peak)
        return self._transcribe(audio)

    def _record_via_sounddevice(
        self,
        *,
        silence_chunks: int,
        max_secs: float,
        warmup_secs: float,
    ) -> np.ndarray | None:
        chunk_frames  = int(SAMPLE_RATE * CHUNK_SECS)
        max_chunks    = int(max_secs / CHUNK_SECS)
        warmup_chunks = max(1, int(warmup_secs / CHUNK_SECS))

        # device=None tells sounddevice to use the Windows default microphone
        # (whatever is selected in Windows Sound Settings → Input).
        frames: list[np.ndarray] = []
        silence_count = 0
        speech_detected = False
        # Start from the persistent noise floor; warmup may raise it further
        noise_floor = self._noise_floor

        log.debug("STT: recording (max=%.1fs, silence=%d chunks)", max_secs, silence_chunks)
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=chunk_frames,
                device=None,   # Windows default microphone
            ) as stream:
                # Short warmup — calibrate noise floor on actual room silence
                warmup_rms_sum = 0.0
                for _ in range(warmup_chunks):
                    block, _ = stream.read(chunk_frames)
                    rms = float(np.sqrt(np.mean(block ** 2)))
                    warmup_rms_sum += rms
                avg_warmup_rms = warmup_rms_sum / warmup_chunks
                # 1.15× gives a small margin above ambient
                noise_floor = max(noise_floor, avg_warmup_rms * 1.15)
                log.debug("STT: noise floor = %.4f (warmup avg rms = %.4f)", noise_floor, avg_warmup_rms)

                for _ in range(max_chunks):
                    block, _ = stream.read(chunk_frames)
                    frames.append(block.copy())
                    rms = float(np.sqrt(np.mean(block ** 2)))

                    if rms >= noise_floor:
                        # Speech detected — reset silence counter
                        speech_detected = True
                        silence_count = 0
                    elif speech_detected:
                        # Only count silence toward exit AFTER speech has started
                        silence_count += 1
                        if silence_count >= silence_chunks:
                            break
                    # If no speech yet, keep waiting for the full max_secs window

        except sd.PortAudioError as e:
            log.error("Microphone error: %s", e)
            return None

        if not speech_detected:
            log.debug("STT: no speech detected in %.1f s window", max_secs)
            return None

        audio = np.concatenate(frames, axis=0).flatten()
        log.debug("STT: recorded %.1f s (speech_detected=True)", len(audio) / SAMPLE_RATE)

        # Update persistent noise floor with a gentle rolling average
        self._noise_floor = 0.8 * self._noise_floor + 0.2 * noise_floor

        return audio

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _transcribe(self, audio: np.ndarray) -> str:
        if self._ensure_whisper():
            return self._transcribe_whisper(audio)
        return self._transcribe_google(audio)

    def _ensure_whisper(self) -> bool:
        if self._whisper is not None:
            return True
        try:
            import whisper
            log.info("Loading Whisper model '%s'", self._model_size)
            self._whisper = whisper.load_model(self._model_size)
            log.info("Whisper ready")
            return True
        except ImportError:
            return False
        except Exception:
            log.exception("Whisper failed to load")
            return False

    def _transcribe_whisper(self, audio: np.ndarray) -> str:
        result = self._whisper.transcribe(audio, language="en", fp16=False)
        text = result["text"].strip()
        log.debug("Whisper: %r", text)
        return text

    def _transcribe_google(self, audio: np.ndarray) -> str:
        """Convert numpy float32 → WAV bytes → sr.AudioData → Google STT."""
        import speech_recognition as sr

        wav_bytes = _ndarray_to_wav(audio)
        audio_data = sr.AudioData(wav_bytes, SAMPLE_RATE, sample_width=2)
        recogniser = sr.Recognizer()
        try:
            text = recogniser.recognize_google(audio_data)
            log.debug("Google STT: %r", text)
            return text
        except sr.UnknownValueError:
            log.debug("STT: speech not understood")
            return ""
        except sr.RequestError as e:
            log.warning("Google STT request failed: %s", e)
            return ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ndarray_to_wav(audio: np.ndarray) -> bytes:
    """Convert float32 mono array to 16-bit PCM WAV bytes."""
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _play_ready_beep() -> None:
    """
    Play a short 880 Hz tone to signal the microphone is opening.
    Runs synchronously (called from executor thread) via winsound.
    Falls back silently on non-Windows or if winsound is unavailable.
    """
    try:
        import winsound
        winsound.Beep(880, 80)   # 880 Hz, 80 ms
    except Exception:
        pass
