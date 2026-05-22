# Lightworks Pro

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-blue.svg)](https://www.microsoft.com/windows)

**A voice-first productivity assistant for blind and visually impaired professionals.**

Lightworks Pro runs silently as a Windows background service, connecting to Microsoft 365 to manage meetings, email, and Teams calls — entirely through voice, with no screen required. It is designed to work *alongside* your existing screen reader (JAWS, NVDA, Fusion, ZoomText), never against it.

---

## Features

- **Meeting alerts** — spoken reminders at 10 min and 5 min before each meeting; automatic join countdown at start time
- **Email Intelligence** — reads your inbox by priority; guided voice wizard for composing and sending
- **Teams calling** — call by name, video call, conference call, extension dial, and PSTN dial — all by voice
- **Consent-first design** — every action follows a Notify → Query → Consent → Execute loop; nothing happens without your explicit voice confirmation
- **Screen reader harmony** — uses `RegisterHotKey` (non-intercepting); hotkeys `Ctrl+Shift+F1–F5` are clear of all standard JAWS, NVDA, Fusion, and ZoomText shortcuts

---

## Requirements

| Requirement | Detail |
|---|---|
| OS | Windows 10 or Windows 11 (64-bit) |
| Python | 3.12 or later |
| Microsoft 365 | Work, school, or personal account |
| Screen reader | JAWS, NVDA, Fusion, ZoomText (optional — app works standalone) |
| Azure App Registration | Free; see setup steps below |

---

## Quick Start

### 1. Clone the repository

```
git clone https://github.com/your-org/lightworks-pro.git
cd lightworks-pro
```

### 2. Install dependencies

```
pip install -r requirements.txt
```

### 3. Register an Azure App (one-time)

Run the included PowerShell script — it creates and configures the Azure App Registration automatically:

```powershell
.\scripts\register_azure_app.ps1
```

If you prefer to register manually, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

### 4. Configure

Copy the example config and fill in your Azure App Client ID:

```
copy config.example.json config.json
```

Edit `config.json` and set `microsoft_client_id` to the Client ID from your Azure App Registration. All other fields have sensible defaults.

### 5. Run

```
python -m lightworks_pro
```

On first run, a voice-guided setup wizard walks you through Microsoft sign-in (browser opens automatically, code copied to clipboard).

---

## Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+Shift+F1` | Listen — activate voice command |
| `Ctrl+Shift+F2` | Read Inbox |
| `Ctrl+Shift+F3` | Next Meeting |
| `Ctrl+Shift+F4` | Teams Call |
| `Ctrl+Shift+F5` | Quit |

---

## Voice Commands

Say any of these after pressing `Ctrl+Shift+F1`:

| Command | Action |
|---|---|
| `"Call [name]"` | Teams audio call to a contact |
| `"Video call [name]"` | Teams video call |
| `"Conference call [name, name]"` | Teams group call |
| `"Extension [number]"` | Internal extension dial |
| `"Dial [number]"` | PSTN phone call |
| `"Read Inbox"` | Start email reading |
| `"Next Meeting"` | Announce next calendar event |
| `"What did I miss"` | Briefing: calls, email, meetings |
| `"Teams Messages"` | Read unread Teams chats |
| `"Test Voice"` | Verify microphone and speaker |

---

## Building the Installer

Requires [PyInstaller](https://pyinstaller.org/) and [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```
pip install pyinstaller
pyinstaller build/lightworks_pro.spec
```

Then open `installer/setup.iss` in Inno Setup Compiler to produce the `.exe` installer.

---

## SharePoint Staff Directory (Optional)

If your organisation stores a staff directory in SharePoint, Lightworks Pro can use it for contact lookup. Add these fields to `config.json`:

```json
"sharepoint_host":      "yourorg.sharepoint.com",
"sharepoint_site_path": "/sites/YourSite",
"sharepoint_file_path": "Lightworks Pro/staff_directory.xlsx"
```

The spreadsheet must have columns: `First Name`, `Last Name`, `Phone`, `Extension`, `Email`.

---

## Project Structure

```
lightworks-pro/
├── core/
│   ├── voice/          # TTS (SAPI5) and STT (Google Web Speech)
│   ├── consent/        # Consent finite state machine
│   ├── meeting/        # Meeting orchestrator and Teams call controls
│   ├── email_intel/    # Email triage, navigation, and compose wizard
│   ├── notifications/  # Alert dispatcher
│   ├── integrations/
│   │   ├── microsoft/  # Microsoft Graph API client and MSAL auth
│   │   └── google/     # Google Workspace client (Gmail, Calendar)
│   └── setup_wizard/   # First-run voice-guided wizard
├── desktop/
│   └── windows/        # System tray service, hotkey daemon
├── mobile/             # iOS (Swift) and Android (Kotlin) — planned
├── native/             # Rust audio engine and hotkey daemon — planned
├── scripts/            # Azure setup, admin consent, installer helpers
├── build/              # PyInstaller spec, hooks, version info
├── installer/          # Inno Setup 6 script
├── docs/               # User guide, roadmap, promo script
├── assets/             # Application icon
├── config.example.json # Configuration template
├── requirements.txt
└── pyproject.toml
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Credits

Developed by **Abu Hoque** at **Lighthouse Guild, New York** — a leading vision rehabilitation organisation serving blind and visually impaired individuals.

## License

[MIT](LICENSE) — Copyright (c) 2026 Abu Hoque & Lighthouse Guild, New York. Free to use, modify, and distribute.
