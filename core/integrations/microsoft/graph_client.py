"""
Microsoft Graph API client — calendar events, mail, presence, Teams chats, and OneNote.
All data retrieved via API (not screen scraping) to ensure AT harmony.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

MEETING_URL_PATTERNS = [
    re.compile(r"https://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+"),
    re.compile(r"https://zoom\.us/[jw]/\d+[^\s\"'<>]*"),
    re.compile(r"https://\w+\.webex\.com/[^\s\"'<>]+"),
    re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}"),
]

def _zoom_deep_link(url: str) -> str:
    """
    Convert a Zoom HTTPS URL to a zoommtg:// deep link that opens Zoom directly.
    Preserves the meeting password so password-protected meetings auto-join.
      https://zoom.us/j/123456789?pwd=AbCdEf  →
      zoommtg://zoom.us/join?action=join&confno=123456789&pwd=AbCdEf
    """
    from urllib.parse import urlparse, parse_qs, urlencode
    parsed = urlparse(url)
    confno = _zoom_id(url)
    params: dict[str, str] = {"action": "join", "confno": confno}
    qs = parse_qs(parsed.query)
    if "pwd" in qs:
        params["pwd"] = qs["pwd"][0]
    return f"zoommtg://zoom.us/join?{urlencode(params)}"


DEEP_LINKS = {
    "teams.microsoft.com": lambda url: url.replace("https://teams.microsoft.com", "msteams://"),
    "zoom.us": _zoom_deep_link,
    "webex.com": lambda url: url,
    "meet.google.com": lambda url: url,
}


@dataclass
class CalendarEvent:
    id: str
    subject: str
    start: datetime
    end: datetime
    organizer_email: str
    is_organizer: bool
    meeting_url: Optional[str]
    deep_link: Optional[str]
    platform: Optional[str]     # "teams" | "zoom" | "webex" | "meet" | None
    body_preview: str = ""


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender_name: str
    sender_email: str
    preview: str
    received_at: datetime
    is_high_priority: bool
    conversation_id: str = ""


@dataclass
class ChatMessage:
    id: str
    chat_id: str
    sender_name: str
    content_preview: str
    received_at: datetime
    chat_topic: Optional[str] = None


class GraphClient:
    def __init__(self, auth, config: dict | None = None) -> None:
        self._auth = auth
        cfg = config or {}
        self._SP_HOST      = cfg.get("sharepoint_host", "")
        self._SP_SITE_PATH = cfg.get("sharepoint_site_path", "")
        self._SP_FILE_PATH = cfg.get("sharepoint_file_path", "")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._auth.get_token()}",
                "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    def events_for_day(self, date: datetime) -> list[CalendarEvent]:
        """Return all calendar events on a given local date."""
        # Work in UTC but align to midnight of the local date
        local_midnight = date.replace(hour=0, minute=0, second=0, microsecond=0,
                                      tzinfo=None)
        start_utc = local_midnight.astimezone(timezone.utc)
        end_utc   = start_utc + timedelta(days=1)
        resp = requests.get(
            f"{GRAPH_BASE}/me/calendarView",
            headers=self._headers(),
            params={
                "startDateTime": start_utc.isoformat(),
                "endDateTime":   end_utc.isoformat(),
                "$top": 20,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,organizer,isOrganizer,bodyPreview,body",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return [self._parse_event(e) for e in resp.json().get("value", [])]

    def upcoming_events(self, count: int = 5) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc).isoformat()
        resp = requests.get(
            f"{GRAPH_BASE}/me/calendarView",
            headers=self._headers(),
            params={
                "startDateTime": now,
                "endDateTime": _hours_from_now(24),
                "$top": count,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,organizer,isOrganizer,bodyPreview,body",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return [self._parse_event(e) for e in resp.json().get("value", [])]

    def _parse_event(self, raw: dict) -> CalendarEvent:
        body = raw.get("body", {}).get("content", "") + raw.get("bodyPreview", "")
        url, platform = _extract_meeting_url(body)
        deep = _to_deep_link(url) if url else None

        return CalendarEvent(
            id=raw["id"],
            subject=raw.get("subject", "(No subject)"),
            start=_parse_dt(raw["start"]["dateTime"]),
            end=_parse_dt(raw["end"]["dateTime"]),
            organizer_email=raw.get("organizer", {}).get("emailAddress", {}).get("address", ""),
            is_organizer=raw.get("isOrganizer", False),
            meeting_url=url,
            deep_link=deep,
            platform=platform,
            body_preview=raw.get("bodyPreview", ""),
        )

    # ------------------------------------------------------------------
    # Mail
    # ------------------------------------------------------------------

    def unread_messages(self, count: int = 10) -> list[EmailMessage]:
        resp = requests.get(
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
            headers=self._headers(),
            params={
                "$filter": "isRead eq false",
                "$top": count,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,sender,receivedDateTime,bodyPreview,importance,conversationId",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return [self._parse_email(m) for m in resp.json().get("value", [])]

    def _parse_email(self, raw: dict) -> EmailMessage:
        sender = raw.get("sender", {}).get("emailAddress", {})
        return EmailMessage(
            id=raw["id"],
            subject=raw.get("subject", "(No subject)"),
            sender_name=sender.get("name", "Unknown"),
            sender_email=sender.get("address", ""),
            preview=raw.get("bodyPreview", ""),
            received_at=_parse_dt(raw["receivedDateTime"]),
            is_high_priority=raw.get("importance", "normal") == "high",
            conversation_id=raw.get("conversationId", ""),
        )

    def delta_inbox_messages(
        self,
        delta_link: str | None = None,
        count: int = 20,
    ) -> tuple[list[EmailMessage], str | None]:
        """
        Incremental inbox sync using Graph $delta.
        First call (delta_link=None): returns all current unread + a delta token.
        Subsequent calls: returns only messages added/changed since the last call.
        Returns (messages, new_delta_link).
        On 410 Gone (expired token), returns ([], None) — caller should re-seed.
        """
        if delta_link:
            url = delta_link
            params: dict = {}
        else:
            url = f"{GRAPH_BASE}/me/mailFolders/inbox/messages/delta"
            params = {
                "$select": "id,subject,sender,receivedDateTime,bodyPreview,importance,conversationId,isRead",
                "$top": count,
            }

        messages: list[EmailMessage] = []
        new_delta_link: str | None = None

        while url:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            params = {}   # only sent on the first request
            if resp.status_code == 410:
                log.warning("Email delta link expired — will re-seed on next cycle")
                return [], None
            resp.raise_for_status()
            data = resp.json()

            for raw in data.get("value", []):
                if "@removed" in raw or raw.get("isRead", False):
                    continue
                messages.append(self._parse_email(raw))

            if "@odata.nextLink" in data:
                url = data["@odata.nextLink"]
            elif "@odata.deltaLink" in data:
                new_delta_link = data["@odata.deltaLink"]
                break
            else:
                break

        return messages, new_delta_link

    def recent_messages(self, hours: int = 1) -> list[EmailMessage]:
        """Messages received in the last N hours (read or unread)."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        resp = requests.get(
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
            headers=self._headers(),
            params={
                "$filter": f"receivedDateTime ge {since}",
                "$top": 20,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,sender,receivedDateTime,bodyPreview,importance,conversationId",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return [self._parse_email(m) for m in resp.json().get("value", [])]

    def latest_in_thread(self, conversation_id: str) -> Optional[EmailMessage]:
        """Return the most recent message in a conversation thread, or None."""
        if not conversation_id:
            return None
        resp = requests.get(
            f"{GRAPH_BASE}/me/messages",
            headers=self._headers(),
            params={
                "$filter": f"conversationId eq '{conversation_id}'",
                "$orderby": "receivedDateTime desc",
                "$top": 1,
                "$select": "id,subject,sender,receivedDateTime,bodyPreview,importance,conversationId",
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])
        return self._parse_email(items[0]) if items else None

    def send_email(self, to: str, subject: str, body: str) -> None:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            }
        }
        resp = requests.post(
            f"{GRAPH_BASE}/me/sendMail",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        log.info("Email sent to %s", to)

    def save_draft(self, to: str, subject: str, body: str) -> None:
        """Save a composed email to the Drafts folder without sending."""
        payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        resp = requests.post(
            f"{GRAPH_BASE}/me/messages",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        log.info("Draft saved for %s", to)

    # ------------------------------------------------------------------
    # Presence
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Teams chats
    # ------------------------------------------------------------------

    def unread_chats(self, count: int = 5) -> list[ChatMessage]:
        """Recent Teams chat messages with last-message preview."""
        resp = requests.get(
            f"{GRAPH_BASE}/me/chats",
            headers=self._headers(),
            params={
                "$expand": "lastMessagePreview",
                "$top": count,
            },
            timeout=10,
        )
        resp.raise_for_status()
        messages: list[ChatMessage] = []
        for chat in resp.json().get("value", []):
            preview = chat.get("lastMessagePreview")
            if not preview or preview.get("isDeleted"):
                continue
            sender_block = preview.get("from") or {}
            sender_user  = sender_block.get("user") or sender_block.get("application") or {}
            sender_name  = sender_user.get("displayName", "Unknown")
            raw_body     = (preview.get("body") or {}).get("content", "")
            body_text    = re.sub(r"<[^>]+>", "", raw_body).strip()
            if not body_text:
                continue
            created = preview.get("createdDateTime", "")
            messages.append(ChatMessage(
                id=preview.get("id", ""),
                chat_id=chat.get("id", ""),
                sender_name=sender_name,
                content_preview=body_text[:200],
                received_at=_parse_dt(created) if created else datetime.now(timezone.utc),
                chat_topic=chat.get("topic") or None,
            ))
        messages.sort(key=lambda m: m.received_at, reverse=True)
        return messages[:count]

    # ------------------------------------------------------------------
    # OneNote
    # ------------------------------------------------------------------

    def create_note(self, title: str, content: str) -> None:
        """Create a OneNote page with a plain-text body."""
        html = (
            f"<html><head><title>{title}</title></head>"
            f"<body><p>{content}</p></body></html>"
        )
        resp = requests.post(
            f"{GRAPH_BASE}/me/onenote/pages",
            headers={
                "Authorization": f"Bearer {self._auth.get_token()}",
                "Content-Type": "application/xhtml+xml",
            },
            data=html.encode("utf-8"),
            timeout=15,
        )
        resp.raise_for_status()
        log.info("OneNote page created: %s", title)

    # ------------------------------------------------------------------
    # Full email body
    # ------------------------------------------------------------------

    def get_message_body(self, message_id: str) -> str:
        """Fetch the full plain-text body of a message (HTML stripped)."""
        resp = requests.get(
            f"{GRAPH_BASE}/me/messages/{message_id}",
            headers=self._headers(),
            params={"$select": "body"},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json().get("body", {})
        content = body.get("content", "")
        content_type = body.get("contentType", "text")
        if content_type.lower() == "html":
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()
        return content

    # ------------------------------------------------------------------
    # Contacts / People
    # ------------------------------------------------------------------

    def get_me(self) -> dict:
        """Return the signed-in user's basic profile (displayName, mail)."""
        resp = requests.get(
            f"{GRAPH_BASE}/me",
            headers=self._headers(),
            params={"$select": "displayName,mail,userPrincipalName"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_people(self, count: int = 200) -> list[dict]:
        """
        Return the user's most relevant people — used for contact pre-caching.
        Tier 1: People API (/me/people — requires People.Read admin consent).
        Tier 2: Outlook contacts book (/me/contacts).
        Tier 3: Org Azure AD directory (/users — requires User.ReadBasic.All).
        """
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/me/people",
                headers=self._headers(),
                params={
                    "$top": count,
                    "$select": "displayName,emailAddresses,jobTitle,department,phones",
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = []
            for person in resp.json().get("value", []):
                emails = person.get("emailAddresses", [])
                phones = person.get("phones", [])
                results.append({
                    "displayName":  person.get("displayName", ""),
                    "emailAddress": emails[0].get("address", "") if emails else "",
                    "jobTitle":     person.get("jobTitle", ""),
                    "department":   person.get("department", ""),
                    "phone":        phones[0].get("number", "") if phones else "",
                })
            if results:
                return results
            log.info("People API returned 0 results — trying contacts book")
        except Exception as e:
            log.warning("People API unavailable (%s) — trying contacts book", e)

        # Tier 2: Outlook personal contacts book
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/me/contacts",
                headers=self._headers(),
                params={
                    "$top": count,
                    "$select": "displayName,emailAddresses,jobTitle,department,businessPhones,mobilePhone",
                },
                timeout=15,
            )
            resp.raise_for_status()
            results = []
            for person in resp.json().get("value", []):
                emails = person.get("emailAddresses", [])
                biz_phones = person.get("businessPhones", [])
                mobile = person.get("mobilePhone", "")
                phone = biz_phones[0] if biz_phones else mobile
                results.append({
                    "displayName":  person.get("displayName", ""),
                    "emailAddress": emails[0].get("address", "") if emails else "",
                    "jobTitle":     person.get("jobTitle", ""),
                    "department":   person.get("department", ""),
                    "phone":        phone,
                })
            if results:
                return results
            log.info("Contacts book returned 0 results — trying org directory")
        except Exception as e:
            log.warning("Contacts book unavailable (%s) — trying org directory", e)

        # Tier 3: Org Azure AD directory (works when People.Read not consented)
        return self._org_users_preload(count)

    def search_contacts(self, query: str, count: int = 3) -> list[dict]:
        """
        Search for a person by name.  Priority order:
          0. Azure AD givenName+surname filter — for "First Last" spoken queries
          1. People API (/me/people) — frequent contacts
          2. Outlook contacts book (/me/contacts)
          3. Azure AD displayName search (/users?$search)
        """
        # Tier 0: precise first+last name search in Azure AD for multi-word queries
        parts = query.strip().split()
        if len(parts) >= 2:
            by_name = self._org_users_by_name(parts[0], parts[-1], count)
            if by_name:
                return by_name

        try:
            resp = requests.get(
                f"{GRAPH_BASE}/me/people",
                headers=self._headers(),
                params={"$search": f'"{query}"', "$top": count,
                        "$select": "displayName,emailAddresses,jobTitle,department,phones"},
                timeout=10,
            )
            resp.raise_for_status()
            results = []
            for person in resp.json().get("value", []):
                emails = person.get("emailAddresses", [])
                phones = person.get("phones", [])
                results.append({
                    "displayName":  person.get("displayName", ""),
                    "emailAddress": emails[0].get("address", "") if emails else "",
                    "jobTitle":     person.get("jobTitle", ""),
                    "department":   person.get("department", ""),
                    "phone":        phones[0].get("number", "") if phones else "",
                })
            if results:
                return results
        except Exception:
            log.warning("People API search failed for %r — trying contacts book", query)

        results = self._contacts_book_search(query, count)
        if results:
            return results

        # Tier 3: Org directory — works even when People.Read is not admin-consented
        return self._org_user_search(query, count)

    def _contacts_book_search(self, query: str, count: int = 3) -> list[dict]:
        """Search Outlook contacts book (/me/contacts) by display name prefix."""
        safe_query = query.replace("'", "''")   # escape single quotes for OData
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/me/contacts",
                headers=self._headers(),
                params={
                    "$filter": f"startswith(displayName,'{safe_query}')",
                    "$top": count,
                    "$select": "displayName,emailAddresses,jobTitle,department,businessPhones,mobilePhone",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            log.warning("Contacts book search failed for %r: %s", query, e)
            return []
        results = []
        for person in resp.json().get("value", []):
            emails = person.get("emailAddresses", [])
            biz_phones = person.get("businessPhones", [])
            mobile = person.get("mobilePhone", "")
            phone = biz_phones[0] if biz_phones else mobile
            results.append({
                "displayName":  person.get("displayName", ""),
                "emailAddress": emails[0].get("address", "") if emails else "",
                "jobTitle":     person.get("jobTitle", ""),
                "department":   person.get("department", ""),
                "phone":        phone,
            })
        return results

    def _org_users_by_name(self, first: str, last: str, count: int = 3) -> list[dict]:
        """
        Search Azure AD users by givenName prefix AND surname prefix.
        'John', 'Smith' → filter=startsWith(givenName,'John') and startsWith(surname,'Smith').
        More precise than a free-text displayName search for spoken first+last queries.
        Requires User.ReadBasic.All scope.
        """
        safe_first = first.replace("'", "''")
        safe_last  = last.replace("'", "''")
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users",
                headers=self._headers(),
                params={
                    "$filter": (
                        f"startsWith(givenName,'{safe_first}') "
                        f"and startsWith(surname,'{safe_last}')"
                    ),
                    "$select": "displayName,mail,userPrincipalName,jobTitle,department,businessPhones",
                    "$top": count,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return self._parse_user_list(resp.json().get("value", []))
        except Exception as e:
            log.debug("Name-parts search (%s + %s) failed: %s", first, last, e)
            return []

    def _org_user_search(self, query: str, count: int = 3) -> list[dict]:
        """Search org Azure AD directory by display name (requires User.ReadBasic.All)."""
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users",
                headers={**self._headers(), "ConsistencyLevel": "eventual"},
                params={
                    "$search": f'"displayName:{query}"',
                    "$select": "displayName,mail,userPrincipalName,jobTitle,department,businessPhones",
                    "$top": count,
                    "$count": "true",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            log.debug("Org directory search failed for %r: %s", query, e)
            return []
        return self._parse_user_list(resp.json().get("value", []))

    def _org_users_preload(self, count: int = 200) -> list[dict]:
        """Preload org users from Azure AD for the startup contact cache."""
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users",
                headers=self._headers(),
                params={
                    "$select": "displayName,mail,userPrincipalName,jobTitle,department,businessPhones",
                    "$top": min(count, 999),
                    "$orderby": "displayName",
                },
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            log.warning("Org user preload failed: %s", e)
            return []
        results = self._parse_user_list(resp.json().get("value", []))
        log.info("Org directory preload: %d users loaded", len(results))
        return results

    def get_user_phone(self, upn: str) -> str:
        """Return the first businessPhone for an Azure AD user by UPN, or ''."""
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/users/{upn}",
                headers=self._headers(),
                params={"$select": "businessPhones"},
                timeout=8,
            )
            resp.raise_for_status()
            phones = resp.json().get("businessPhones", [])
            return phones[0] if phones else ""
        except Exception as e:
            log.debug("get_user_phone(%s) failed: %s", upn, e)
            return ""

    def _parse_user_list(self, users: list) -> list[dict]:
        """Convert /users API response items to the standard contact dict format."""
        results = []
        for user in users:
            display = user.get("displayName", "")
            # Prefer UPN over mail — Teams identifies users by UPN
            email = user.get("userPrincipalName") or user.get("mail", "")
            if not display or not email:
                continue
            phones = user.get("businessPhones", [])
            results.append({
                "displayName":  display,
                "emailAddress": email,
                "jobTitle":     user.get("jobTitle", ""),
                "department":   user.get("department", ""),
                "phone":        phones[0] if phones else "",
            })
        return results

    # ------------------------------------------------------------------
    # SharePoint staff directory
    # ------------------------------------------------------------------

    def get_sharepoint_directory(self) -> list[dict]:
        """
        Read staff_directory.xlsx from SharePoint via Microsoft Graph.
        Columns expected: First Name, Last Name, Phone, Extension, Email
        Returns contacts in the standard cache dict format.
        Requires Sites.Read.All scope.
        """
        from urllib.parse import quote as _quote
        file_encoded = _quote(self._SP_FILE_PATH, safe="/")
        try:
            site_resp = requests.get(
                f"{GRAPH_BASE}/sites/{self._SP_HOST}:{self._SP_SITE_PATH}",
                headers=self._headers(),
                timeout=15,
            )
            site_resp.raise_for_status()
            site_id = site_resp.json()["id"]

            sheets_resp = requests.get(
                f"{GRAPH_BASE}/sites/{site_id}/drive/root:/{file_encoded}:/workbook/worksheets",
                headers=self._headers(),
                timeout=15,
            )
            sheets_resp.raise_for_status()
            sheets = sheets_resp.json().get("value", [])
            if not sheets:
                log.warning("SharePoint staff_directory.xlsx: no worksheets found")
                return []
            sheet_name = _quote(sheets[0]["name"], safe="")

            range_resp = requests.get(
                f"{GRAPH_BASE}/sites/{site_id}/drive/root:/{file_encoded}"
                f":/workbook/worksheets/{sheet_name}/usedRange",
                headers=self._headers(),
                params={"$select": "values"},
                timeout=30,
            )
            range_resp.raise_for_status()
            values = range_resp.json().get("values", [])
            return self._parse_staff_directory(values)
        except Exception as e:
            log.warning("SharePoint staff directory unavailable: %s", e)
            return []

    def _parse_staff_directory(self, values: list[list]) -> list[dict]:
        """Parse 2-D Excel usedRange values into contact dicts. Row 0 is the header."""
        if len(values) < 2:
            return []

        headers = [str(h).strip().lower() for h in values[0]]

        def _col(*names: str) -> int:
            for n in names:
                try:
                    return headers.index(n.lower())
                except ValueError:
                    pass
            return -1

        i_first = _col("first name")
        i_last  = _col("last name")
        i_phone = _col("phone")
        i_ext   = _col("extension")
        i_email = _col("email")

        def _cell(row: list, i: int) -> str:
            if i < 0 or i >= len(row):
                return ""
            v = row[i]
            return str(v).strip() if v is not None and v != "" else ""

        results = []
        for row in values[1:]:
            first = _cell(row, i_first)
            last  = _cell(row, i_last)
            if not first and not last:
                continue
            results.append({
                "displayName":  f"{first} {last}".strip(),
                "emailAddress": _cell(row, i_email),
                "phone":        _cell(row, i_phone),
                "extension":    _cell(row, i_ext),
                "jobTitle":     "",
                "department":   "",
                "_source":      "sharepoint",
            })

        log.info("SharePoint staff directory: %d contacts loaded", len(results))
        return results

    # ------------------------------------------------------------------
    # Microsoft To Do
    # ------------------------------------------------------------------

    def get_todo_lists(self) -> list:
        """Return all To Do lists as TodoList dataclass objects."""
        from core.todo.engine import TodoList
        resp = requests.get(
            f"{GRAPH_BASE}/me/todo/lists",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return [
            TodoList(
                id=lst["id"],
                display_name=lst.get("displayName", ""),
                is_default=lst.get("wellknownListName") == "defaultList",
            )
            for lst in resp.json().get("value", [])
        ]

    def get_todo_tasks(self, list_id: str, count: int = 20) -> list:
        """Return pending (non-completed) tasks for a list."""
        from core.todo.engine import TodoTask
        resp = requests.get(
            f"{GRAPH_BASE}/me/todo/lists/{list_id}/tasks",
            headers=self._headers(),
            params={
                "$filter": "status ne 'completed'",
                "$top": count,
                "$select": "id,title,importance,status,dueDateTime",
            },
            timeout=10,
        )
        resp.raise_for_status()
        tasks = []
        for t in resp.json().get("value", []):
            due_raw  = (t.get("dueDateTime") or {}).get("dateTime")
            due_zone = (t.get("dueDateTime") or {}).get("timeZone", "UTC")
            due_dt   = _parse_dt(due_raw) if due_raw else None
            tasks.append(TodoTask(
                id=t["id"],
                list_id=list_id,
                title=t.get("title", "(No title)"),
                importance=t.get("importance", "normal"),
                status=t.get("status", "notStarted"),
                due_date=due_dt,
            ))
        return tasks

    def add_todo_task(self, list_id: str, title: str, importance: str = "normal") -> None:
        resp = requests.post(
            f"{GRAPH_BASE}/me/todo/lists/{list_id}/tasks",
            headers=self._headers(),
            json={"title": title, "importance": importance},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("To Do task created: %s", title)

    def complete_todo_task(self, list_id: str, task_id: str) -> None:
        resp = requests.patch(
            f"{GRAPH_BASE}/me/todo/lists/{list_id}/tasks/{task_id}",
            headers=self._headers(),
            json={"status": "completed"},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("To Do task %s marked complete", task_id)

    def set_presence(self, availability: str, activity: str) -> None:
        """
        availability: "Available" | "Busy" | "DoNotDisturb" | "Away"
        activity: "InAMeeting" | "Available" | etc.
        """
        payload = {
            "sessionId": "lightworks-pro",
            "availability": availability,
            "activity": activity,
            "expirationDuration": "PT1H",
        }
        resp = requests.post(
            f"{GRAPH_BASE}/me/presence/setPresence",
            headers=self._headers(),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_meeting_url(text: str) -> tuple[Optional[str], Optional[str]]:
    platforms = {
        "teams.microsoft.com": "teams",
        "zoom.us": "zoom",
        "webex.com": "webex",
        "meet.google.com": "meet",
    }
    for pattern in MEETING_URL_PATTERNS:
        m = pattern.search(text)
        if m:
            url = m.group(0)
            for domain, name in platforms.items():
                if domain in url:
                    return url, name
    return None, None


def _to_deep_link(url: str) -> Optional[str]:
    for domain, transform in DEEP_LINKS.items():
        if domain in url:
            return transform(url)
    return url


def _zoom_id(url: str) -> str:
    m = re.search(r"/[jw]/(\d+)", url)
    return m.group(1) if m else ""


def _parse_dt(s: str) -> datetime:
    s = s.rstrip("Z") + "+00:00"
    return datetime.fromisoformat(s)


def _hours_from_now(h: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()
