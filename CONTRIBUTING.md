# Contributing to Lightworks Pro

Thank you for your interest in contributing. Lightworks Pro is built for blind and visually impaired professionals, so accessibility is a core requirement — not a stretch goal.

---

## Code of Conduct

Be respectful. Contributions from people with disabilities and assistive technology users are especially valued and should be welcomed accordingly.

---

## Getting Started

### Prerequisites

- Python 3.12 or later
- Windows 10 or 11 (for full testing; core logic can be developed on any OS)
- A Microsoft 365 account (for integration testing)
- Optionally: JAWS, NVDA, Fusion, or ZoomText for AT harmony testing

### Set up a development environment

```bash
git clone https://github.com/your-org/lightworks-pro.git
cd lightworks-pro
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
# Edit config.json with your Azure App Client ID
python -m lightworks_pro
```

---

## What to Work On

Check the open GitHub Issues. Good first issues are labelled `good first issue`. The [ROADMAP.md](docs/ROADMAP.md) describes planned phases.

---

## Submitting Changes

1. Fork the repo and create a feature branch (`git checkout -b feature/your-feature`)
2. Make your changes
3. Test manually — see testing guidance below
4. Open a Pull Request with a clear description of what changed and why

---

## Testing Guidelines

There is no automated test suite yet — integration testing against a real Microsoft 365 tenant is the most meaningful check.

**Before submitting a PR, verify:**

- [ ] The app launches without errors (`python -m lightworks_pro`)
- [ ] Hotkeys `Ctrl+Shift+F1` through `Ctrl+Shift+F5` work correctly
- [ ] TTS speaks clearly and does not freeze
- [ ] If you changed hotkeys or audio: test with JAWS or NVDA running simultaneously to confirm no AT conflicts

**AT Harmony Rules (non-negotiable):**

- Never use `SetWindowsHookEx` — use `RegisterHotKey` only
- Never inject into display drivers
- Hotkeys must not overlap with JAWS (`Insert+*`), NVDA (`Caps Lock+*`), or standard AT shortcuts
- Route all speech through the system audio session (not an exclusive-mode stream)
- Never block the SAPI5 speech queue — use a dedicated COM STA worker thread

---

## Reporting Bugs

Open a GitHub Issue with:
- What you expected to happen
- What actually happened
- Your screen reader name and version (if relevant)
- Windows version
- Any log output from `%APPDATA%\LightworksPro\logs\`

---

## Security Issues

Do **not** open a public GitHub Issue for security vulnerabilities. See [SECURITY.md](SECURITY.md).
