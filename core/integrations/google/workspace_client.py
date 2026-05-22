"""
Google Workspace API client — Gmail and Calendar via official google-api-python-client.
OAuth 2.0 tokens stored in OS keychain (never on disk unencrypted).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

MEET_URL_RE = re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}")


@dataclass
class GCalEvent:
    id: str
    summary: str
    start: datetime
    end: datetime
    is_organizer: bool
    meet_url: Optional[str]
    conference_type: Optional[str]


@dataclass
class GmailMessage:
    id: str
    thread_id: str
    subject: str
    sender_name: str
    sender_email: str
    snippet: str
    date: datetime
    is_important: bool


class WorkspaceClient:
    def __init__(self, credentials: Credentials) -> None:
        self._creds = credentials
        self._calendar = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        self._gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    def upcoming_events(self, count: int = 5) -> list[GCalEvent]:
        now = datetime.now(timezone.utc).isoformat()
        result = (
            self._calendar.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=count,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [self._parse_event(e) for e in result.get("items", [])]

    def _parse_event(self, raw: dict) -> GCalEvent:
        conf = raw.get("conferenceData", {})
        entry_points = conf.get("entryPoints", [])
        meet_url = next(
            (ep["uri"] for ep in entry_points if ep.get("entryPointType") == "video"),
            None,
        )
        if not meet_url:
            # Fall back to scanning description
            m = MEET_URL_RE.search(raw.get("description", ""))
            meet_url = m.group(0) if m else None

        organizer_email = raw.get("organizer", {}).get("email", "")
        user_email = self._my_email()
        is_organizer = organizer_email == user_email

        return GCalEvent(
            id=raw["id"],
            summary=raw.get("summary", "(No title)"),
            start=_parse_dt(raw["start"].get("dateTime", raw["start"].get("date", ""))),
            end=_parse_dt(raw["end"].get("dateTime", raw["end"].get("date", ""))),
            is_organizer=is_organizer,
            meet_url=meet_url,
            conference_type=conf.get("conferenceSolution", {}).get("name"),
        )

    def _my_email(self) -> str:
        profile = self._gmail.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")

    # ------------------------------------------------------------------
    # Gmail
    # ------------------------------------------------------------------

    def unread_messages(self, count: int = 10) -> list[GmailMessage]:
        result = (
            self._gmail.users()
            .messages()
            .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=count)
            .execute()
        )
        messages = []
        for item in result.get("messages", []):
            msg = self._gmail.users().messages().get(
                userId="me", id=item["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            messages.append(self._parse_message(msg))
        return messages

    def _parse_message(self, raw: dict) -> GmailMessage:
        headers = {h["name"]: h["value"] for h in raw.get("payload", {}).get("headers", [])}
        sender_raw = headers.get("From", "")
        name, email = _parse_sender(sender_raw)
        return GmailMessage(
            id=raw["id"],
            thread_id=raw["threadId"],
            subject=headers.get("Subject", "(No subject)"),
            sender_name=name,
            sender_email=email,
            snippet=raw.get("snippet", ""),
            date=_parse_dt(headers.get("Date", "")),
            is_important="IMPORTANT" in raw.get("labelIds", []),
        )

    def send_message(self, to: str, subject: str, body: str) -> None:
        import base64
        from email.message import EmailMessage as StdEmail

        msg = StdEmail()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self._gmail.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        log.info("Gmail sent to %s", to)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_dt(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc) if "T" not in s and "," not in s else datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _parse_sender(raw: str) -> tuple[str, str]:
    m = re.match(r'"?([^"<]+)"?\s*<([^>]+)>', raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    if "@" in raw:
        return raw.strip(), raw.strip()
    return raw.strip(), ""
