# Lightworks Pro — Technical Roadmap
**Last updated: May 2026 · Version 1.2.0**

---

## Executive Summary

Lightworks Pro is a UI-less, Voice User Interface (VUI) productivity assistant for blind and visually impaired professionals. It operates as a background service between the OS and Microsoft 365, enforcing a strict **Notification → Query → Consent → Execution** loop for every action that affects the user's data or communications.

Phase 1 (Windows desktop) is **complete and shipping**. Phases 2–4 cover mobile platforms, Google Workspace integration, and hardening.

---

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Business logic / orchestration | Python 3.14 | Rich API ecosystem, rapid iteration |
| TTS engine | `win32com` → `SAPI.SpVoice` | Direct SAPI5 COM call — no pyttsx3 event loop issues |
| STT engine | SpeechRecognition + Google Web Speech | Whisper blocked on Python 3.14 bindings; re-enabled when available |
| Global hotkey daemon | Win32 `RegisterHotKey` via `ctypes` | Non-intercepting; delivers copy of keypress, never consumes it |
| Microsoft Graph client | `msal` + `requests` | Device-code OAuth flow; DPAPI-encrypted token cache |
| Token cache | DPAPI-encrypted file (`win32crypt`) | Replaces Windows Credential Manager (2 KB size limit incompatible with MSAL cache) |
| Desktop packaging | PyInstaller + Inno Setup 6 | Per-user install, no admin required |
| iOS app | Swift (planned) | AVSpeech, SFSpeechRecognizer |
| Android app | Kotlin (planned) | Jetpack, Android SpeechRecognizer |

### Why SAPI5 via `win32com` instead of pyttsx3?

pyttsx3's `runAndWait()` uses a COM event sink that can hang on the second call in some Windows configurations — `endUtterance` never fires, freezing the TTS worker thread permanently. Calling `SAPI.SpVoice.Speak()` directly is a single blocking COM call with no internal event loop, which is reliable across all tested configurations.

### Why DPAPI file cache instead of Windows Credential Manager?

The MSAL `SerializableTokenCache` serialises to JSON, which typically exceeds the 2,560-byte hard limit of `CredWrite`. Storing the encrypted blob as a file in `%APPDATA%\LightworksPro\` removes the size constraint. DPAPI (`CryptProtectData`) provides the same Windows-user-scoped encryption guarantee.

### Why `Ctrl+Shift+F1/F2/F3/F4` for hotkeys?

JAWS claims most `Ctrl+Alt+*` and `Insert+*` combinations. NVDA claims `Caps Lock+*` and some `Ctrl+Alt+*` combinations. `Ctrl+Shift+F1–F4` is unused by all tested screen readers across all default configurations.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    USER (voice / hotkey)                    │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│              VOICE LAYER  (Lightworks Pro)                  │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │  STT Engine  │   │ Consent FSM  │   │  TTS Engine    │  │
│  │  (Google /   │──▶│  (state      │──▶│  (SAPI5 via    │  │
│  │   Whisper*)  │   │   machine)   │   │   win32com)    │  │
│  └──────────────┘   └──────┬───────┘   └────────────────┘  │
│                            │                                │
│  ┌─────────────────────────▼────────────────────────────┐   │
│  │              Orchestration Bus                       │   │
│  │  ┌───────────┐  ┌────────────┐  ┌────────────────┐  │   │
│  │  │ Meeting   │  │  Email     │  │  Notification  │  │   │
│  │  │Orchestrat.│  │Intelligence│  │    Engine      │  │   │
│  │  └─────┬─────┘  └─────┬──────┘  └───────┬────────┘  │   │
│  └────────┼──────────────┼─────────────────┼────────────┘   │
│           │              │                 │                │
│  ┌────────▼──────────────▼─────────────────▼────────────┐   │
│  │                Integration Adapters                  │   │
│  │   Microsoft Graph API    │   Google Workspace (v1.2) │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌────────────────────────┐  ┌──────────────────────────┐   │
│  │ Hotkey Daemon          │  │ Audio Ducking Engine      │   │
│  │ (Win32 RegisterHotKey) │  │ (planned: Rust / WASAPI)  │   │
│  └────────────────────────┘  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│          EXISTING ASSISTIVE TECHNOLOGY (untouched)          │
│       JAWS  │  NVDA  │  Fusion  │  ZoomText                 │
└─────────────────────────────────────────────────────────────┘
```

*\* Whisper STT pending Python 3.14 compatible bindings.*

---

## AT Harmony Rules (non-negotiable)

1. Never call `SetWindowsHookEx` — use `RegisterHotKey` only.
2. Never inject into display drivers or use `DirectInput`.
3. Hotkeys must not overlap with JAWS (`Insert+*`), NVDA (`Caps Lock+*`), or standard AT shortcuts. **Resolved: Ctrl+Shift+F1/F2/F3/F4.**
4. Route all speech through the system audio session, not a new exclusive-mode stream.
5. Never block the SAPI5 speech queue — use a dedicated COM STA worker thread.

---

## Phase 1 — Windows Desktop (Complete)

### Delivered

- [x] Background service — Windows system tray via `pystray`
- [x] Global hotkeys — `Ctrl+Shift+F1/F2/F3/F4` via Win32 `RegisterHotKey` (non-intercepting)
- [x] TTS engine — `SAPI.SpVoice` via `win32com`, priority queue, dedicated COM STA thread
- [x] STT engine — sounddevice capture with explicit device enumeration (PyInstaller compatible), Google Web Speech API transcription
- [x] Consent FSM — IDLE → NOTIFICATION → QUERY → LISTENING → CONFIRMED/REJECTED → EXECUTING
- [x] Microsoft Graph OAuth — MSAL device-code flow, DPAPI-encrypted file token cache
- [x] Accessible sign-in — browser opens automatically, code copied to clipboard, spoken instructions
- [x] Meeting Orchestrator — calendar polling every 20 s, advance alerts at **10 min and 5 min** (announce only), auto-join countdown at start time; host and participant handled identically; cancel words narrowed to "cancel / don't / not now" to prevent false cancellation from JAWS/Fusion reading Teams notification buttons
- [x] Meeting deep links — `msteams://`, `zoommtg://`, browser fallback for Webex and Google Meet
- [x] Email Intelligence Suite — inbox triage with high-priority detection, interactive "next" navigation
- [x] Proactive email notifications — background poll every 15 minutes, announces new arrivals only
- [x] Voice command dispatch — guided listen prompt, all commands with spoken help
- [x] First-run setup wizard — fully voice-driven, no visual UI required
- [x] Azure App auto-registration — PowerShell script creates and configures the app registration (Graph REST, no PS module; duplicate-safe; runtime permission ID resolution)
- [x] Per-user installer — Inno Setup 6, no admin rights required, JAWS/NVDA accessible installer UI
- [x] Teams calling — dial by name, dial by phone number (PSTN), video call, conference call (multi-user)
- [x] Contact name disambiguation by voice — if two contacts share a name, announces both with department and asks "say first or second"
- [x] Contact search resilience — People API (`/me/people`) with automatic fallback to Outlook contacts book (`/me/contacts`) when People API is unavailable or returns no results; applies to both live search and startup preload
- [x] People.Read admin consent helper — `scripts/grant_admin_consent.py` opens Azure consent URL in browser and clears stale token cache; `auth.get_admin_consent_url()` and `auth.clear_cache()` support programmatic reset
- [x] Contact cache startup warning — spoken alert at launch when contact directory is empty, with guidance to run the consent script
- [x] Incoming call detection — polls visible window titles every 3 s, announces caller, prompts answer/decline via Consent FSM; covers classic Teams and new Teams 2024 (`"is calling"`, `"calling you"` title patterns)
- [x] Mute Guard audio pulse — two-beep confirmation on mute toggle (880 Hz → 660 Hz, 100 ms each, AT-safe winsound.Beep)
- [x] Compose email by voice — "compose email to [name] about [subject]" routes to EmailIntelSuite
- [x] Auto-mute on join — configurable flag mutes microphone automatically after joining a Teams or Zoom meeting
- [x] Presence sync — sets Teams availability to Busy/InAMeeting on join, resets to Available after meeting end + 5 min buffer

### Known gaps carried to v1.3

- Whisper STT (offline) — pending Python 3.14 compatible wheel
- Audio ducking — implemented as placeholder; Rust/WASAPI integration pending
- Interactive email reply navigation by voice

---

## Phase 2 — Google Workspace & Enhancements (v1.2 target)

### Deliverables

- [ ] Google OAuth — `google-auth` + device flow or installed-app flow
- [ ] Gmail adapter — unread fetch, send via `gmail.users.messages.send`
- [ ] Google Calendar adapter — event fetch, Meet link extraction
- [ ] Whisper STT — re-enable when Python 3.14 compatible bindings are available
- [ ] Audio ducking — Rust/WASAPI implementation, skip AT process audio sessions
- [ ] Interactive email reply — navigate to specific message by voice, dictate and send
- [ ] Delta sync — Graph `$delta` queries to replace polling where push is unavailable

---

## Phase 3 — Mobile (v1.3 target)

### Deliverables

- [ ] iOS: Swift background service, AVSpeechSynthesizer, SFSpeechRecognizer
- [ ] iOS: FaceID/TouchID consent gate
- [ ] iOS: Pocket Mode (headset-only audio path)
- [ ] Android: Kotlin foreground service, SpeechRecognizer, BiometricPrompt
- [ ] Android: Mute Guard haptic (Android Vibrator) on mute toggle
- [ ] Presence Sync — Graph `/presence` PATCH on meeting join/leave (Windows and mobile)

---

## Phase 4 — Hardening & Enterprise (v1.4 target)

### Deliverables

- [ ] Multiple Microsoft 365 accounts — switch between work and school accounts
- [ ] Local STT enforcement policy — config flag to block cloud speech fallback
- [ ] Audit log — every consented action recorded locally with timestamp and outcome
- [ ] AT regression test suite — automated against JAWS 2024, NVDA 2024, Fusion 2024
- [ ] MDM/Group Policy support — enterprise config deployment
- [ ] macOS menu bar app — rumps-based, mirrors Windows feature set

---

## Directory Structure (current)

```
Lightworks Pro/
├── core/
│   ├── voice/
│   │   ├── stt_engine.py             # sounddevice capture + Google STT
│   │   └── tts_engine.py             # SAPI5 via win32com, priority queue
│   ├── consent/
│   │   └── state_machine.py          # Consent FSM
│   ├── integrations/
│   │   └── microsoft/
│   │       ├── auth.py               # MSAL device-code + DPAPI file cache; clear_cache(), get_admin_consent_url()
│   │       └── graph_client.py       # Graph API: calendar, mail, presence, contacts with People→book fallback
│   ├── meeting/
│   │   ├── orchestrator.py           # 10/5-min alerts, deep-link launch, auto-mute, presence sync
│   │   └── controls.py               # Hotkey send to Teams/Zoom, dial_teams(), incoming call detection (classic + new Teams 2024)
│   ├── email_intel/
│   │   └── suite.py                  # Triage, "next" navigation, 15-min polling
│   ├── notifications/
│   │   └── engine.py                 # Alert dispatcher
│   └── setup_wizard/
│       └── wizard.py                 # Voice-driven first-run wizard
├── desktop/
│   └── windows/
│       └── tray_service.py           # System tray, hotkeys, service orchestration, contact cache + empty-cache warning
├── scripts/
│   ├── register_azure_app.ps1        # One-time Azure App Registration (PowerShell)
│   ├── set_microsoft_client_id.py    # Manual Client ID helper
│   └── grant_admin_consent.py        # Opens Azure admin consent URL + clears token cache (fixes People.Read issues)
├── installer/
│   └── setup.iss                     # Inno Setup 6 script (includes scripts\ in {app}\scripts\)
├── build/
│   └── lightworks_pro.spec           # PyInstaller spec
├── docs/
│   ├── USER_GUIDE.md
│   ├── ROADMAP.md
│   └── Lightworks_Pro_Presentation.pptx
├── assets/
│   └── lightworks_pro.ico
└── __main__.py                       # Entry point
```

---

## Milestones

| Milestone | Status | Notes |
|---|---|---|
| M1: Consent FSM + TTS/STT loop | **Complete** | SAPI5 via win32com, STT via sounddevice |
| M2: Microsoft Graph auth + calendar | **Complete** | MSAL device-code, DPAPI cache |
| M3: Meeting Orchestrator | **Complete** | 10 min + 5 min alerts, deep links |
| M4: Email Intelligence | **Complete** | Triage, "next" nav, 15-min notifications |
| M5: Accessible sign-in flow | **Complete** | Browser auto-open, clipboard code copy |
| M6: Azure App auto-registration | **Complete** | PowerShell REST-based script |
| M7: Per-user installer | **Complete** | Inno Setup 6, no admin required |
| M8: Teams calling (dial/receive/conference/video) | **Complete** | msteams:// deep links; PSTN via 4: prefix |
| M9: Incoming call detection + Mute Guard | **Complete** | win32gui window polling; winsound.Beep pulse; new Teams 2024 title patterns |
| M10: Compose email by voice | **Complete** | "compose email to [name] about [subject]" |
| M11: Contact search resilience + admin consent | **Complete** | People API → contacts book fallback; grant_admin_consent.py; contact cache warning |
| M12: Contact name disambiguation | **Complete** | Announces both matches with department; "say first or second" |
| M13: Google Workspace parity | Planned v1.2 | |
| M14: Whisper STT (offline) | Planned v1.2 | Blocked on Python 3.14 bindings |
| M15: Audio ducking (Rust/WASAPI) | Planned v1.2 | |
| M16: iOS app | Planned v1.3 | |
| M17: Android app | Planned v1.3 | |
| M18: AT regression suite | Planned v1.4 | |
