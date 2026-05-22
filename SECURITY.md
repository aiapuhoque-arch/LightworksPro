# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.1.x | Yes |
| < 1.1 | No |

---

## Reporting a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Please report security issues by email. Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

You will receive a response within 5 business days. We will work with you to understand and address the issue before any public disclosure.

---

## Security Design

Lightworks Pro is designed with the following security properties:

**No credentials in source code**
All API credentials are user-supplied via `config.json` (never committed) or obtained at runtime via OAuth device-code flow.

**Token storage**
Microsoft Graph tokens are cached in `%APPDATA%\LightworksPro\msal_cache_*.bin`, encrypted at rest using Windows DPAPI (`CryptProtectData`) — scoped to the current Windows user account.

**Consent before every action**
Every action that reads or modifies user data (email, calendar, calls) goes through the Consent FSM. The user must explicitly say YES before any action executes. There is no silent automation.

**No screen scraping or injection**
The application uses only documented Microsoft Graph REST APIs. It does not inject into other processes, intercept keystrokes system-wide, or access display drivers.

**Minimum required permissions**
The Azure App Registration requests only the Microsoft Graph scopes it needs:
- `Calendars.Read`
- `Mail.Read`, `Mail.Send`
- `People.Read`
- `Presence.ReadWrite`
- `Chat.Read`
- `OnlineMeetings.ReadWrite`
- `Sites.Read.All` (SharePoint staff directory — optional)
