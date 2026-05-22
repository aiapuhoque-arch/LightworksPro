# Changelog

All notable changes to Lightworks Pro are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/).

---

## [1.1.0] — 2026-05-22 — Initial Open-Source Release

### Added
- MIT license; public GitHub release
- `config.example.json` — configuration template with SharePoint fields
- SharePoint host, site, and file path now read from `config.json` (no longer hardcoded)
- `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, `.gitignore`

### Changed
- `pyproject.toml` license field updated from Proprietary to MIT

---

## [1.0.0] — 2026-01-01 — Phase 1 Complete (Windows Desktop)

### Added
- Background service — Windows system tray via `pystray`
- Global hotkeys — `Ctrl+Shift+F1/F2/F3/F4/F5` via Win32 `RegisterHotKey` (non-intercepting)
- TTS engine — `SAPI.SpVoice` via `win32com`, priority queue, dedicated COM STA thread
- STT engine — `sounddevice` capture with explicit device enumeration, Google Web Speech API
- Consent FSM — IDLE → NOTIFICATION → QUERY → LISTENING → CONFIRMED/REJECTED → EXECUTING
- Microsoft Graph OAuth — MSAL device-code flow, DPAPI-encrypted file token cache
- Accessible sign-in — browser opens automatically, code copied to clipboard, spoken instructions
- Meeting Orchestrator — calendar polling every 20 s, advance alerts at 10 min and 5 min, auto-join countdown
- Meeting deep links — `msteams://`, `zoommtg://`, browser fallback for Webex and Google Meet
- Email Intelligence Suite — inbox triage with high-priority detection, interactive navigation
- Proactive email notifications — background poll every 15 minutes, announces new arrivals only
- Voice command dispatch — guided listen prompt, all commands with spoken help
- First-run setup wizard — fully voice-driven, no visual UI required
- Azure App auto-registration — PowerShell script creates and configures the app registration
- Per-user installer — Inno Setup 6, no admin rights required, JAWS/NVDA accessible
- Teams calling — audio call, video call, conference call, extension dial, PSTN dial
- Contact name disambiguation — announces both matches with department; "say first or second"
- Contact search resilience — People API with automatic fallback to Outlook contacts book
- Incoming call detection — polls window titles, announces caller, prompts answer/decline
- Mute Guard audio pulse — two-beep confirmation on mute toggle (AT-safe `winsound.Beep`)
- Compose email by voice — guided step-by-step wizard (recipient, subject, body)
- Auto-mute on join — configurable flag mutes microphone automatically after joining
- Presence sync — sets Teams availability to Busy/InAMeeting on join, resets after meeting end
