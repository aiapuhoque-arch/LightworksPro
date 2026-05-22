"""
First-run voice setup wizard — entirely voice-driven so the user never needs
to interact with a visual UI. Runs once after installation, writes config.json
to %APPDATA%\\LightworksPro\\config.json, and optionally registers Windows startup.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from core.voice.tts_engine import TTSEngine
from core.voice.stt_engine import STTEngine
from core.consent.state_machine import AFFIRMATIVES, NEGATIVES
from core.startup.windows_startup import config_path, register, is_registered

log = logging.getLogger(__name__)

LISTEN_TIMEOUT = 10.0


class SetupWizard:
    def __init__(self) -> None:
        self._tts = TTSEngine()
        self._stt = STTEngine()

    async def run(self) -> dict:
        """
        Run the full wizard and return the completed config dict.
        Writes config.json to AppData before returning.
        """
        await self._speak(
            "Welcome to Lightworks Pro. "
            "I will guide you through a short setup. "
            "Answer each question by saying yes or no."
        )

        config: dict = {
            "whisper_model": "small",
            "tts": {"rate": 185, "volume": 1.0},
            "audio_duck_volume": 0.2,
            "local_stt_only": False,
            "log_level": "INFO",
        }

        # --- Microsoft 365 ---
        if await self._ask_yes_no(
            "Would you like to connect Microsoft 365? "
            "This enables your calendar, email, and Teams meetings."
        ):
            client_id = await self._collect_client_id()
            if client_id:
                config["microsoft_client_id"] = client_id
                config["microsoft_tenant_id"] = "common"
                await self._speak(
                    "Microsoft 365 has been configured. "
                    "You will be asked to sign in the first time you use it."
                )
            else:
                await self._speak(
                    "Microsoft 365 setup skipped. "
                    "You can add it later by editing config.json in your AppData folder."
                )

        # --- Windows startup ---
        if not is_registered():
            if await self._ask_yes_no(
                "Should Lightworks Pro start automatically every time Windows starts?"
            ):
                try:
                    register()
                    await self._speak("Done. Lightworks Pro will start with Windows.")
                except Exception:
                    log.exception("Could not register startup")
                    await self._speak(
                        "I could not register the startup entry. "
                        "You can run Lightworks Pro manually from the Start Menu."
                    )

        # --- Speech rate preference ---
        if await self._ask_yes_no(
            "Would you like me to speak faster? "
            "The current speed is comfortable for most users. "
            "Say yes to increase the speed."
        ):
            config["tts"]["rate"] = 240
            await self._speak("Speech rate increased.")

        # --- Save ---
        cfg_file = config_path()
        cfg_file.write_text(json.dumps(config, indent=2))
        log.info("Config written to %s", cfg_file)

        await self._speak(
            "Setup complete. "
            "Lightworks Pro is now ready. "
            "Press Control Shift F1 at any time to give a voice command. "
            "Press Control Shift F2 for your inbox, "
            "or Control Shift F3 for your next meeting. "
            "You can also right-click the tray icon in the system tray."
        )
        return config

    # ------------------------------------------------------------------
    # Wizard steps
    # ------------------------------------------------------------------

    async def _collect_client_id(self) -> str:
        """
        Instruct the user to find their Azure App Client ID.
        In production this would walk through the device-code OAuth flow.
        For now it asks the user to speak the client ID digit by digit,
        or skip.
        """
        await self._speak(
            "To connect Microsoft 365, you need an Azure App Client ID. "
            "If you have one, say it now. "
            "Otherwise say skip and I will set up Microsoft 365 later."
        )
        response = await self._listen()
        if not response or "skip" in response.lower():
            return ""
        # Filter to alphanumeric and hyphens (UUID format)
        cleaned = "".join(c for c in response if c.isalnum() or c == "-").lower()
        if len(cleaned) >= 30:
            await self._speak(f"I heard: {response}. Is that correct? Say yes or no.")
            confirm = await self._listen()
            if confirm and any(w in confirm.lower() for w in AFFIRMATIVES):
                return cleaned
        await self._speak(
            "I could not capture a valid Client ID. "
            "You can add it later by editing config.json."
        )
        return ""

    async def _ask_yes_no(self, question: str) -> bool:
        await self._speak(question)
        response = await self._listen()
        if not response:
            return False
        words = response.lower().split()
        return any(w in AFFIRMATIVES for w in words)

    async def _speak(self, text: str) -> None:
        await self._tts.speak(text, priority="normal")

    async def _listen(self) -> str:
        try:
            return await asyncio.wait_for(
                self._stt.listen_once(), timeout=LISTEN_TIMEOUT
            )
        except asyncio.TimeoutError:
            return ""
