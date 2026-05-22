# Lightworks Pro — User Guide
**Version 1.2.0 · Windows Edition · May 2026**

---

## Table of Contents

1. [What Is Lightworks Pro?](#what-is-lightworks-pro)
2. [Supported Windows Versions](#supported-windows-versions)
3. [System Requirements](#system-requirements)
4. [Assistive Technology Compatibility](#assistive-technology-compatibility)
5. [Installation](#installation)
6. [First-Run Setup Wizard](#first-run-setup-wizard)
7. [Global Hotkeys](#global-hotkeys)
8. [Daily Use — Voice Commands](#daily-use--voice-commands)
9. [The Consent System](#the-consent-system)
10. [Email Features](#email-features)
11. [Meeting Features](#meeting-features)
12. [Teams Calling Features](#teams-calling-features)
13. [Audio Behaviour](#audio-behaviour)
14. [Connecting Microsoft 365](#connecting-microsoft-365)
15. [Windows Startup](#windows-startup)
16. [Uninstalling](#uninstalling)
17. [Troubleshooting](#troubleshooting)
18. [Privacy and Security](#privacy-and-security)
19. [Known Limitations in Version 1.2](#known-limitations-in-version-12)

---

## What Is Lightworks Pro?

Lightworks Pro is a **voice-controlled productivity assistant** built for blind and visually impaired professionals. It runs quietly in your system tray and connects to your Microsoft 365 account to help you manage emails, calendar events, and online meetings — entirely through voice, without touching a visual interface.

It is designed to coexist with your existing screen reader. It never intercepts keystrokes used by JAWS, NVDA, Fusion, or ZoomText, and it speaks through the same audio system you have already configured.

---

## Supported Windows Versions

| Windows Version | Edition | Architecture | Support Status |
|---|---|---|---|
| Windows 11 24H2 | Home, Pro, Enterprise, Education | 64-bit | **Fully supported** |
| Windows 11 23H2 | Home, Pro, Enterprise, Education | 64-bit | **Fully supported** |
| Windows 11 22H2 | Home, Pro, Enterprise, Education | 64-bit | **Fully supported** |
| Windows 11 21H2 | Home, Pro, Enterprise, Education | 64-bit | **Fully supported** |
| Windows 10 22H2 | Home, Pro, Enterprise, Education | 64-bit | **Fully supported** |
| Windows 10 21H2 | Home, Pro, Enterprise, Education | 64-bit | **Fully supported** |
| Windows 10 21H1 | Home, Pro, Enterprise, Education | 64-bit | Supported |
| Windows 10 20H2 | Home, Pro, Enterprise, Education | 64-bit | Supported |
| Windows Server 2022 | Standard, Datacenter | 64-bit | Supported (no tray icon on Server Core) |
| Windows Server 2019 | Standard, Datacenter | 64-bit | Supported |
| Windows 10 32-bit (any) | Any | 32-bit | **Not supported** |
| Windows 8.1 and earlier | Any | Any | **Not supported** |
| Windows 11 on ARM | Any | ARM64 | Not tested — may work via x64 emulation |

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| Processor | 64-bit dual-core, 1.6 GHz | Quad-core, 2.0 GHz or faster |
| RAM | 2 GB | 4 GB or more |
| Disk space | 300 MB free | 500 MB free |
| Microphone | Any Windows-compatible microphone | Noise-cancelling USB or Bluetooth headset |
| Internet | Required for Microsoft 365 | Broadband (2 Mbps or faster) |
| Audio output | Any Windows audio device | Bluetooth headset with HFP profile |

---

## Assistive Technology Compatibility

Lightworks Pro is designed to operate alongside your existing assistive technology without any conflicts.

| Software | Version Tested | Status |
|---|---|---|
| JAWS for Windows | 2022, 2023, 2024 | **Compatible** — no hotkey conflicts |
| NVDA | 2022.1 through 2024.4 | **Compatible** — no hotkey conflicts |
| Fusion | 2022, 2023, 2024 | **Compatible** — no conflicts |
| ZoomText | 2022, 2023, 2024 | **Compatible** — audio path not affected |
| Windows Narrator | All versions on Windows 10/11 | **Compatible** |
| SuperNova | 21, 22, 23 | Compatible (not formally tested) |

### How coexistence works

- Hotkeys use **Ctrl+Shift+F1/F2/F3/F4** — function key combinations that JAWS and NVDA do not claim by default. They are registered via `RegisterHotKey`, which delivers a copy of the keypress to Lightworks Pro without consuming it. Your screen reader receives the same key normally.
- Speech output goes through **SAPI5** (`SAPI.SpVoice` via Windows COM) — the same engine your screen reader uses. Both voices play through the same audio device simultaneously. If JAWS or Fusion speaks at the same moment as Lightworks Pro, you will hear both at once; Lightworks Pro leaves brief pauses after announcements to minimise overlap.
- Lightworks Pro does **not** use display hooks, DirectInput, low-level keyboard hooks, or graphics injection.

---

## Installation

### Step 1 — Download the installer

Obtain the file `LightworksPro_Setup_1.2.0.exe` from your distribution source.

### Step 2 — Run the installer

Run `LightworksPro_Setup_1.2.0.exe`. The installer is fully accessible with JAWS and NVDA.

You will be asked:

- **Installation folder** — defaults to your user's Program Files folder. No administrator password is required.
- **Start automatically with Windows** — recommended.
- **Create a desktop shortcut** — optional.

### Step 3 — Launch

After installation you can launch immediately. The first-run setup wizard will start automatically.

### Step 4 — Connect Microsoft 365 (optional but recommended)

After the wizard, run the included registration script to create your Azure App and connect your account. See [Connecting Microsoft 365](#connecting-microsoft-365).

### Silent installation (IT administrators)

```
LightworksPro_Setup_1.2.0.exe /VERYSILENT /NORESTART /TASKS="startup"
```

---

## First-Run Setup Wizard

On the very first launch, Lightworks Pro speaks a voice-guided setup wizard:

1. **Welcome** — explains what to expect.
2. **Microsoft 365** — "Would you like to connect Microsoft 365?" Say **yes** or **no**.
3. **Windows startup** — "Should Lightworks Pro start automatically when Windows starts?"
4. **Speech rate** — "Would you like me to speak faster?"
5. **Completion** — "Setup complete. Lightworks Pro is now ready. Press Control Shift F1 at any time to give a voice command."

To re-run the wizard: right-click the tray icon → **Re-run Setup**, or run `LightworksPro.exe --setup`.

---

## Global Hotkeys

Lightworks Pro registers four global hotkeys that work system-wide, even when another window is in focus. They use **Ctrl+Shift+F1–F4** — chosen specifically to avoid conflicts with JAWS and NVDA.

| Hotkey | Action |
|---|---|
| **Ctrl + Shift + F1** | Start listening for a voice command |
| **Ctrl + Shift + F2** | Read unread email inbox immediately |
| **Ctrl + Shift + F3** | Read your next scheduled meeting immediately |
| **Ctrl + Shift + F4** | Open Teams calling — dial by name, number, or start a conference |

> If a hotkey does not respond, another application may have claimed it. Lightworks Pro will announce this on startup: "Could not register: Control Shift F2." You can still use all features by pressing Ctrl+Shift+F1 and speaking the command name.

---

## Daily Use — Voice Commands

Press **Ctrl+Shift+F1** to open the microphone. Lightworks Pro will say what it is listening for, then wait for your command.

### What it says when listening

*"Listening. You can say: inbox, next meeting, today, tomorrow, call followed by a name, my tasks, add task, compose email, weather, remind me, or help. You have 15 seconds after the beep."*

### Available commands

| What you say | What happens |
|---|---|
| **Email and calendar** | |
| "Inbox" / "Email" / "Messages" | Opens interactive inbox — navigate with "next" |
| "Next meeting" / "Calendar" / "Schedule" | Reads your next upcoming meeting |
| "Today" / "Tomorrow" | Reads your full schedule for that day |
| "Compose email to [name] about [subject]" | Dictate and send a new email |
| "Teams messages" / "Chat messages" | Reads recent Teams chat messages |
| **Meeting controls (while in a meeting)** | |
| "Mute" / "Unmute" / "Toggle mute" | Mute or unmute your microphone — confirmed by two audio beeps |
| "Camera on" / "Camera off" | Turn your camera on or off |
| "Raise hand" / "Hand up" | Raise your hand in the meeting |
| "Leave" / "End call" / "Hang up" / "Leave meeting" | Leave the current meeting |
| **Calling (Teams)** | |
| "Call [name]" | Start a voice call with a contact by name |
| "Video call [name]" | Start a video call with a contact by name |
| "Dial [phone number]" | Call a phone number via Teams PSTN |
| "Extension [number]" | Dial an internal extension via Teams |
| "Conference call with [name] and [name]" | Start a group call with multiple contacts |
| **Incoming calls** | |
| *(automatic — no hotkey needed)* | Lightworks Pro announces the caller and asks whether to answer |
| **Tasks and notes** | |
| "My tasks" / "To do list" | Reads pending tasks — high priority first |
| "Add task [title]" | Creates a new task in Microsoft To Do |
| "Complete task [name]" | Marks a task as done |
| "Create note" | Dictate a note saved to OneNote |
| **Contacts and status** | |
| "Who is [name]" / "Find contact [name]" | Looks up a contact's details |
| "Set status busy / available / do not disturb" | Updates your Teams presence |
| **System** | |
| "What time is it" | Speaks the current time |
| "Battery" | Speaks your battery level |
| "Weather" | Speaks current weather conditions |
| "Remind me in [time] about [subject]" | Sets a spoken reminder |
| "What did I miss" | Briefing of recent emails and upcoming meetings |
| "Repeat that" | Repeats the last thing spoken |
| "Help" / "Commands" | Full spoken guide to all features |
| "Test" | Confirms voice output is working |
| "Quit" / "Exit" | Closes Lightworks Pro |

---

## The Consent System

Lightworks Pro **never takes an action without your explicit permission**. Every action follows this sequence:

```
NOTIFICATION  →  QUERY  →  LISTEN  →  EXECUTE (or CANCEL)
```

### Example — Meeting about to start

1. **Notification**: "You have a Teams meeting starting in 5 minutes. Subject: Weekly standup."
2. **Query**: "Should I join as participant?"
3. **Listen**: Lightworks Pro waits up to 12 seconds for your response.
4. **Execute or cancel**:
   - Say **yes**, **join**, **go**, **ok**, or **sure** → Teams opens and joins the meeting.
   - Say **no**, **cancel**, **skip**, or **not now** → No action taken.
   - No response for 12 seconds → Automatically cancelled.

### Words that count as "yes"
yes, yeah, yep, ok, okay, sure, do it, join, send, start, go, confirm, proceed

### Words that count as "no"
no, nope, cancel, stop, don't, skip, abort, not now, later, dismiss

> **Meeting start-time auto-join** uses a narrower set: only **"cancel"**, **"don't"**, and **"not now"** are recognised. "stop", "no", and "skip" are excluded because JAWS and Fusion read those words from Teams notification buttons, which can cause a false cancellation.

---

## Email Features

### Proactive new-email notifications

Lightworks Pro checks for new emails every **15 minutes** in the background. When new messages arrive, it announces them automatically — no hotkey needed.

- **One new email**: *"New email. High priority. From John Smith. Subject: Urgent review needed."*
- **Multiple new emails**: *"3 new emails. 1 high priority. Press Control Shift F2 to read them."*

Notifications are only spoken when new messages actually arrive. If nothing is new, nothing is said.

### Inbox with "next" navigation

Press **Ctrl+Shift+F2** or say "inbox" to read your unread messages one at a time.

Lightworks Pro starts with a summary:
*"You have 4 unread messages. 1 high priority. Say next after each one, or stop to exit."*

Then for each email:
*"Message 1 of 4. High priority. From Sarah Johnson. Subject: Deadline moved. The project deadline has been moved to Friday. Please confirm you can still deliver."*

After each message it waits and says: *"Say next for the next email, or stop to exit."*

- Say **"next"** → moves to the next message
- Say **"stop"** (or "done", "exit", "enough") → exits inbox
- Say nothing for 6 seconds → automatically moves on

High-priority messages are always read first.

### High-priority detection

An email is flagged high priority if Microsoft marks it as important, or if the subject or preview contains words like: *urgent, asap, action required, deadline, critical, immediately, time sensitive, response needed.*

### Dictating a reply

After hearing an email, say "reply" and follow the prompts:

1. Speak your reply. Say "done" when finished.
2. Lightworks Pro reads the draft back to you.
3. It asks: "Ready to send?"
4. Say "yes" to send, "no" to cancel.

Nothing is sent without your explicit confirmation.

---

## Meeting Features

### Automatic meeting alerts — 10 minutes and 5 minutes

Lightworks Pro checks your calendar every 20 seconds. When a calendar event with an online meeting link is coming up, it speaks an advance announcement automatically at **both 10 minutes and 5 minutes** before the start time. These are reminders only — no action is required.

**10-minute reminder**: *"Reminder: you have a Teams meeting in 10 minutes as participant. Subject: Weekly standup."*

**5-minute reminder**: *"Reminder: you have a Teams meeting in 5 minutes as participant. Subject: Weekly standup."*

### Automatic join at start time

When a meeting reaches its scheduled start time, Lightworks Pro announces it and automatically opens the meeting app after a 15-second countdown:

*"Your Teams meeting is starting now: Weekly standup. Joining as participant in 15 seconds. Say cancel to abort."*

Say **"cancel"**, **"don't"**, or **"not now"** within 15 seconds to stop the automatic join. If you say nothing, the meeting app opens and you are joined automatically. This works the same whether you are the host or a participant.

### Supported platforms

| Platform | Deep link | What opens |
|---|---|---|
| Microsoft Teams | `msteams://` | Teams desktop app, directly in meeting |
| Zoom | `zoommtg://` | Zoom desktop app, directly in meeting |
| Cisco Webex | Browser URL | Webex in your default browser |
| Google Meet | Browser URL | Meet in your default browser |

### Host vs. participant

Lightworks Pro detects your role from the calendar invite and names it in the start-time announcement:

- *"Joining as **host** in 15 seconds. Say cancel to abort."*
- *"Joining as **participant** in 15 seconds. Say cancel to abort."*

The automatic join behaviour is identical for both roles.

### On-demand: next meeting

Press **Ctrl+Shift+F3** at any time to hear your next upcoming meeting:
*"Your next meeting is in 22 minutes. Teams: Weekly standup. You are a participant."*

---

## Teams Calling Features

Lightworks Pro integrates with Microsoft Teams to let you place and receive calls entirely by voice. Press **Ctrl+Shift+F4** or say "call [name]" after pressing Ctrl+Shift+F1.

### Calling a contact by name

Say "call [name]" — for example, "call John Smith". Lightworks Pro searches your Microsoft 365 contacts directory and confirms the match before dialling.

- *"John Smith from IT. Call — say stop to cancel."* — silence or **yes** dials; say **stop** to cancel.
- If two contacts share a similar name, Lightworks Pro announces both with their department and asks: *"Two people found: John Smith from IT, or John Adams from Finance. Say first or second."*
- Contact search uses the Microsoft 365 People directory first, then falls back to your Outlook contacts book automatically.

For a video call, say "video call [name]".

### Calling a phone number

Say "dial [number]" — for example, "dial zero four four seven nine one two three..." Lightworks Pro captures the digits, normalises the number to international format, and asks for confirmation before dialling.

- Ten-digit US/Canada numbers are automatically prefixed as +1.
- The call is placed via Teams PSTN — the recipient's phone rings normally.
- Requires a Teams Phone System licence on your Microsoft 365 account.

### Internal extensions

Say "extension [number]" — for example, "extension 1234". Lightworks Pro dials the internal extension via Teams.

### Conference calls

Say "conference call with [name] and [name]" — for example, "conference call with John and Sarah". Lightworks Pro looks up each contact and dials all of them simultaneously.

- If a contact is not found, Lightworks Pro announces who was skipped and continues with the others.
- Confirmed as a group before dialling: *"John Smith and Sarah Johnson. Conference call — say stop to cancel."*

### Incoming call detection

Lightworks Pro continuously watches for incoming Teams and Zoom call notifications. When a call arrives:

1. *"Incoming Teams call from John Smith. Should I answer?"*
2. Say **yes** or **answer** to pick up, or **no** or **decline** to reject.
3. If you do not respond within 12 seconds, the call is automatically declined and recorded as a missed call.

Works with both classic Teams and new Microsoft Teams (2024). Works even if Teams is in the background.

### Missed calls

Say **"what did I miss"** to hear a summary of missed calls alongside recent emails and upcoming meetings.

### Mute Guard — audio pulse on mute toggle

When you say "mute" or "unmute" during a meeting, Lightworks Pro sends the mute toggle to the meeting app and immediately plays two short audio beeps (880 Hz then 660 Hz). These beeps confirm the toggle was sent **without speaking aloud** — so other participants do not hear the announcement.

### Supported call types

| Command | Result |
|---|---|
| "Call [contact name]" | Teams voice call to contact's email address |
| "Video call [contact name]" | Teams video call to contact's email address |
| "Dial / Phone [number]" | Teams PSTN call to a phone number |
| "Extension [number]" | Teams internal extension call |
| "Conference call with [name] and [name]" | Teams group voice call |
| Incoming call notification | Automatic — announces caller and prompts for answer/decline |

---

## Audio Behaviour

### Priority levels

- **Alert** — spoken immediately, interrupts queued speech. Used for meeting alerts, consent questions, and error messages.
- **Normal** — spoken in order. Used for inbox summaries and informational messages.

### Speech rate

The default speech rate is comfortable for most users. To adjust, say "faster", "slower", or "normal speed" — or re-run the setup wizard.

---

## Connecting Microsoft 365

### IT Administrator — do this once only

Run the registration script from PowerShell **on any one machine**, signed in with an account that has Azure AD Application Administrator or Global Administrator rights:

```powershell
pwsh -File "scripts\register_azure_app.ps1"
```

This script:
1. Opens a sign-in page in your browser automatically.
2. Creates the Lightworks Pro app registration in your Microsoft 365 tenant.
3. Saves the Client ID to the config file on the machine where you run it.
4. Outputs the Client ID — **copy and keep this value**, you will share it with users.

> This step only needs to be done **once per organisation**, not once per user.

---

### Each User — run setup_user.ps1 (no admin rights needed)

Every user installing Lightworks Pro on their machine runs this single script. No Azure permissions, no browser sign-in, no administrator required:

```powershell
pwsh -File "scripts\setup_user.ps1" -ClientId "YOUR-CLIENT-ID-HERE"
```

The script writes the Client ID to `%APPDATA%\LightworksPro\config.json` and exits.

---

### Step — Sign in to Microsoft 365 (first launch only)

After running `setup_user.ps1`, launch Lightworks Pro. On first use it will:

1. Open the Microsoft sign-in page in your default browser automatically.
2. Copy the sign-in code to your clipboard.
3. Speak instructions to complete the sign-in.
4. Wait for you to complete sign-in in the browser.
5. Announce: *"Microsoft 365 connected. Calendar and email are now active."*

After this one-time sign-in, credentials are saved and you will stay connected across restarts.

### Grant admin consent for contact search (if needed)

If contact search does not work (calling by name fails, or you hear *"contact directory is empty"* on startup), your organisation may require an administrator to approve the People directory permission.

Run the included consent helper script:

```
python "{app}\scripts\grant_admin_consent.py"
```

Or locate it at: `%LOCALAPPDATA%\Programs\Lightworks Pro\scripts\grant_admin_consent.py`

The script will:
1. Open your browser to the Microsoft admin consent page for the Lightworks Pro app.
2. Ask you (or your IT admin) to sign in and click **Accept**.
3. Automatically clear the stored sign-in token.
4. Instruct you to restart Lightworks Pro to re-authenticate with the new permissions.

> **For IT administrators:** If users in your organisation cannot search contacts, visit the admin consent URL listed in the script output and accept on behalf of your organisation. This is a one-time step per tenant.

### Credential storage

Sign-in tokens are stored in a **DPAPI-encrypted file** at `%APPDATA%\LightworksPro\msal_cache_*.bin`. DPAPI encryption is tied to your Windows user account — only you can read the file on this computer. No passwords are ever stored.

---

## Windows Startup

If you chose automatic startup during setup, Lightworks Pro adds an entry to:

```
HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run
```

This is a per-user, no-admin entry — it only starts when you log in.

---

## Uninstalling

### From Settings

1. Open **Settings → Apps → Installed apps**.
2. Find **Lightworks Pro** and click **Uninstall**.

### Silent uninstall

```
"%LOCALAPPDATA%\Programs\Lightworks Pro\unins000.exe" /VERYSILENT /NORESTART
```

### What is removed

- Application files from the installation folder.
- Windows startup registry entry.
- Start Menu shortcuts.

### What is kept

- Your configuration: `%APPDATA%\LightworksPro\config.json`
- Your sign-in token cache: `%APPDATA%\LightworksPro\msal_cache_*.bin`

To remove these manually:

```
rmdir /s /q "%APPDATA%\LightworksPro"
```

---

## Troubleshooting

### Lightworks Pro does not speak after installation

- Confirm your audio device is set as the default in Windows Sound settings.
- Confirm a SAPI5 voice is installed: **Settings → Time & Language → Speech**.
- Right-click the tray icon → **Test Voice**.

### A hotkey does not respond

Another application has claimed that key combination. Check `%APPDATA%\LightworksPro\logs\lightworks_pro.log` for a line like `"RegisterHotKey FAILED: Control Shift F2"`. You can still use all features by pressing Ctrl+Shift+F1 and speaking the command.

### Meeting alerts are not spoken

- Confirm Microsoft 365 is connected (you heard "Microsoft 365 connected" on startup).
- The meeting invite must contain a supported meeting link in the **body** of the invite. Links in attachments cannot be detected.
- Lightworks Pro checks the calendar every 30 seconds. Alerts fire at 10 minutes and 5 minutes before start.

### Email notifications are not appearing

- Lightworks Pro checks for new email every 15 minutes. If no new emails have arrived since the last check, nothing is announced.
- Confirm Microsoft 365 is connected.

### Microsoft 365 sign-in fails

- Ensure you have a stable internet connection during sign-in.
- Use a **work or school** account, not a personal @outlook.com account.
- If your organisation uses conditional access policies, contact your IT administrator to confirm the Lightworks Pro app is authorised.
- To retry: restart Lightworks Pro from the tray icon.

### Contact search fails / "Call [name]" does not find anyone

This is usually a Microsoft 365 permissions issue. Follow these steps in order:

1. **Check sign-in** — confirm Lightworks Pro announced "Microsoft 365 connected" on last startup.
2. **Run the consent script** — if you heard *"contact directory is empty"* on startup, run:
   ```
   python "%LOCALAPPDATA%\Programs\Lightworks Pro\scripts\grant_admin_consent.py"
   ```
   Sign in with an admin account (or ask your organisation's IT administrator to do so), click **Accept**, then restart Lightworks Pro.
3. **Re-authenticate** — if the above does not help, the stored token may be outdated. Delete `%APPDATA%\LightworksPro\msal_cache_*.bin` and restart; Lightworks Pro will sign you in again and request fresh permissions.
4. **Check the log** — open `%APPDATA%\LightworksPro\logs\lightworks_pro.log` and look for lines containing `People API` or `contacts book` to see which step failed and why.

### Incoming call is not announced

- Confirm Teams is open (not just in the system tray — the main Teams window must be running).
- Classic Teams and new Teams 2024 are both supported.
- If Teams is open but calls are still not detected, check whether Teams is showing the call notification as a Windows toast only (no separate window). In that case, enable the **"Show call notifications in a separate window"** option in Teams Settings → Calls.

### Speech recognition does not understand me

- Speak clearly after hearing the listening prompt. Pause briefly before speaking.
- Reduce background noise. A headset microphone gives much better results than a built-in laptop microphone.
- Keep commands short: "inbox", "next meeting", "help".

---

## Privacy and Security

| Area | How Lightworks Pro handles it |
|---|---|
| **Voice processing** | Processed locally on your device. No audio is recorded or stored. |
| **Email content** | Read via Microsoft Graph API. Spoken to you and never stored locally or transmitted elsewhere. |
| **Calendar data** | Read via Microsoft Graph API. Used only to detect upcoming meetings. Never stored or transmitted. |
| **Credentials** | OAuth 2.0 tokens stored in a DPAPI-encrypted file in your AppData folder. Passwords are never seen or stored. |
| **Logging** | Logs written to `%APPDATA%\LightworksPro\logs\`. Contain operational events only — not email content or personal data. |
| **No telemetry** | Lightworks Pro does not send usage data, crash reports, or analytics to any server. |

### Microsoft 365 permissions requested

| Permission | Why it is needed |
|---|---|
| `Calendars.Read` | Read your calendar to detect upcoming meetings |
| `Mail.Read` | Read your inbox for the email summary and notification features |
| `Mail.Send` | Send replies and new emails you have dictated and confirmed |
| `MailboxSettings.Read` | Read your timezone and working hours for accurate time display |
| `Presence.ReadWrite` | Update your Teams availability status when you join or leave a meeting |
| `Chat.Read` | Read Teams chat context for meeting-related notifications |
| `Notes.ReadWrite` | Access OneNote for voice-dictated notes |
| `People.Read` | Look up contacts by name when you say "call [name]" — may require admin consent in some organisations |
| `Contacts.Read` | Fallback contact search via Outlook contacts book when People directory is unavailable |
| `Tasks.ReadWrite` | Read and create tasks from voice commands |

---

## Known Limitations in Version 1.2

- **Google Workspace** (Gmail, Google Meet, Google Calendar) — not yet connected. Planned for version 1.2 feature update.
- **Whisper STT** (fully offline) — not yet available for Python 3.14. The Google Web Speech API fallback is used for now. Will be enabled automatically in a future update.
- **Email reply by voice** — the "reply" voice command is implemented but navigating to a specific message by voice is not yet available. Full interactive reply flow planned for a future update.
- **macOS, iOS, Android** — not yet released. Windows is the Phase 1 platform.
- **Multiple Microsoft 365 accounts** — only one account can be connected at a time.
- **Meeting detection in recurring events** — may miss the first occurrence if the invite was sent before Lightworks Pro was installed.
- **Teams incoming calls (toast-only notifications)** — if your Teams is configured to show incoming calls as Windows toast notifications only (no separate window), Lightworks Pro may not detect them. Enable "Show call notifications in a separate window" in Teams Settings → Calls to resolve this.
- **PSTN calling** — requires a Microsoft Teams Phone System licence. Without it, "dial [number]" commands will not connect.
- **Simultaneous speech (JAWS / ZoomText Fusion)** — Lightworks Pro and your screen reader both use SAPI5. If both speak at the same moment, the voices overlap briefly. Lightworks Pro leaves pauses after meeting alerts and consent prompts to reduce this; it cannot prevent all overlap.

---

*Lightworks Pro — Built for blind professionals, by accessible design.*
*Version 1.2.0 · May 2026 · Abu Hoque & Lighthouse Guild, New York*
