"""
Email Intelligence Suite — inbox triage, proactive new-mail notifications,
interactive "next" navigation, full-body reading, dictation reply, quiet hours,
verbosity control, and consent-gated send.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.consent.state_machine import ConsentFSM, ConsentRequest

log = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "stop", "done", "exit", "enough", "quit", "no", "end",
    "leave", "cancel", "close", "finished", "that's all", "thats all",
})

_NEXT_WORDS = frozenset({
    "next", "continue", "go", "forward", "skip", "more", "yes", "okay", "ok",
})


def _is_stop_command(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    return any(w in t for w in _STOP_WORDS)


def _is_next_command(text: str) -> bool:
    if not text:
        return True   # silence or no recognition → auto-advance
    t = text.lower().strip()
    return any(w in t for w in _NEXT_WORDS)


HIGH_PRIORITY_KEYWORDS = frozenset({
    "urgent", "asap", "action required", "deadline", "critical",
    "immediately", "time sensitive", "response needed",
})

EMAIL_POLL_SECONDS = 60      # check for new email every 60 seconds (delta sync)
CHAT_POLL_SECONDS  = 30      # check for new Teams messages every 30 seconds
PRE_LISTEN_SETTLE_SECS = 0.2


class EmailIntelSuite:
    def __init__(self, consent_fsm: ConsentFSM, tts, stt, *mail_clients) -> None:
        self._fsm = consent_fsm
        self._tts = tts
        self._stt = stt
        self._clients = mail_clients
        self._seen_ids: set[str] = set()
        self._seen_chat_ids: set[str] = set()
        self._seeded = False
        self._chats_seeded = False
        self._email_delta_link: str | None = None
        # Verbosity: "normal" (full detail) or "terse" (shorter announcements)
        self.verbosity: str = "normal"
        # Quiet hours: when set, suppress background notifications until this time
        self._quiet_until: Optional[datetime] = None
        # Track the message being navigated for "read full" / "reply" mid-session
        self._current_message = None

    # ------------------------------------------------------------------
    # Background polling — call as an asyncio task
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Seed known IDs, then run email and Teams chat polling concurrently."""
        await asyncio.gather(self._seed(), self._seed_chats())
        await asyncio.gather(self._poll_email(), self._poll_chats())

    async def _poll_email(self) -> None:
        while True:
            await asyncio.sleep(EMAIL_POLL_SECONDS)
            try:
                new = await self._fetch_new_since_seed()
                if new:
                    await self._announce_new_email(new)
            except Exception:
                log.exception("Email polling error")

    async def _poll_chats(self) -> None:
        while True:
            await asyncio.sleep(CHAT_POLL_SECONDS)
            try:
                chats = await self._fetch_chats(20)
                new = [c for c in chats if c.id not in self._seen_chat_ids]
                for c in new:
                    self._seen_chat_ids.add(c.id)
                if new:
                    await self._announce_new_chats(new)
            except Exception:
                log.exception("Teams chat polling error")

    async def _seed(self) -> None:
        try:
            msgs, delta_link = await self._fetch_delta(delta_link=None, count=50)
            self._seen_ids = {m.id for m in msgs}
            self._email_delta_link = delta_link
            self._seeded = True
            log.info(
                "Email: seeded %d known unread IDs (delta=%s)",
                len(self._seen_ids),
                "yes" if delta_link else "no",
            )
        except Exception:
            log.exception("Email: seed failed")

    async def _seed_chats(self) -> None:
        try:
            chats = await self._fetch_chats(30)
            self._seen_chat_ids = {c.id for c in chats}
            self._chats_seeded = True
            log.info("Teams chats: seeded %d known message IDs", len(self._seen_chat_ids))
        except Exception:
            log.exception("Teams chats: seed failed")

    def _is_quiet(self) -> bool:
        if self._quiet_until is None:
            return False
        if datetime.now(timezone.utc) < self._quiet_until:
            return True
        self._quiet_until = None   # expired
        return False

    def set_quiet_hours(self, minutes: int) -> None:
        from datetime import timedelta
        self._quiet_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    async def _announce_new_email(self, messages: list) -> None:
        if self._is_quiet():
            return
        count = len(messages)
        if count == 1:
            m = messages[0]
            priority_tag = "High priority. " if self._is_high_priority(m) else ""
            if self.verbosity == "terse":
                text = (
                    f"New email. {priority_tag}{m.sender_name}. {m.subject}."
                )
            else:
                text = (
                    f"New email. {priority_tag}"
                    f"From {m.sender_name}. "
                    f"Subject: {m.subject}. "
                    f"{m.preview[:120]} "
                    "Say reply to respond."
                )
            await self._tts.speak(text, priority="normal")

            # Brief listen for immediate reply
            if self.verbosity != "terse":
                await asyncio.sleep(0.2)
                listen_fn = getattr(self._stt, "listen_command", self._stt.listen_once)
                response = await listen_fn()
                if response and "reply" in response.lower():
                    await self.dictate_reply(m)
        else:
            high = sum(1 for m in messages if self._is_high_priority(m))
            msg = f"{count} new emails."
            if high:
                msg += f" {high} high priority."
            if self.verbosity != "terse":
                msg += " Press Control Shift F2 to read them."
            await self._tts.speak(msg, priority="normal")

    async def _announce_new_chats(self, messages: list) -> None:
        if self._is_quiet():
            return
        count = len(messages)
        if count == 1:
            m = messages[0]
            chat_label = f"in {m.chat_topic}" if m.chat_topic else "in a Teams chat"
            if self.verbosity == "terse":
                text = f"Teams message. {m.sender_name}: {m.content_preview[:80]}"
            else:
                text = (
                    f"New Teams message from {m.sender_name} {chat_label}. "
                    f"{m.content_preview[:120]}"
                )
            await self._tts.speak(text, priority="normal")
        else:
            await self._tts.speak(
                f"{count} new Teams messages. "
                "Press Control Shift F1 and say Teams messages to read them.",
                priority="normal",
            )

    # ------------------------------------------------------------------
    # On-demand inbox — interactive "next" navigation
    # ------------------------------------------------------------------

    async def announce_inbox(self, count: int = 5) -> None:
        messages = await self._fetch_unread(count)
        if not messages:
            await self._tts.speak(
                "Your inbox is clear. No unread messages.", priority="normal"
            )
            return

        high    = [m for m in messages if self._is_high_priority(m)]
        normal  = [m for m in messages if not self._is_high_priority(m)]
        ordered = high + normal
        total   = len(ordered)

        summary = f"You have {total} unread message{'s' if total > 1 else ''}."
        if high:
            summary += f" {len(high)} high priority."
        if self.verbosity == "terse":
            summary += " Say next or stop."
        else:
            summary += " Say next to move between messages, read full for the full body, reply to respond, or stop to exit."
        await self._tts.speak(summary, priority="normal")

        for i, m in enumerate(ordered):
            self._current_message = m
            priority_tag = "High priority. " if self._is_high_priority(m) else ""
            position = f"Message {i + 1} of {total}. "

            # Thread context
            thread_suffix = ""
            if self.verbosity != "terse":
                latest = await self._latest_in_thread(m)
                if latest and latest.id != m.id:
                    thread_suffix = (
                        f" Latest reply from {latest.sender_name}: "
                        f"{latest.preview[:120]}"
                    )

            preview_len = 80 if self.verbosity == "terse" else 150
            await self._tts.speak(
                f"{position}{priority_tag}"
                f"From {m.sender_name}. "
                f"Subject: {m.subject}. "
                f"{m.preview[:preview_len]}"
                f"{thread_suffix}",
                priority="normal",
            )

            nav_prompt = "Say next or stop." if self.verbosity == "terse" else \
                         "Say next, read full, reply, or stop."
            await self._tts.speak(nav_prompt, priority="normal")
            response = await self._listen_brief()

            if _is_stop_command(response):
                await self._tts.speak("Exiting inbox.", priority="normal")
                self._current_message = None
                return

            if response and any(w in response.lower() for w in ("read full", "full", "read more", "more")):
                await self._read_full_body(m)
                # After reading full, ask again
                await self._tts.speak("Say next, reply, or stop.", priority="normal")
                response = await self._listen_brief()
                if _is_stop_command(response):
                    await self._tts.speak("Exiting inbox.", priority="normal")
                    self._current_message = None
                    return

            if response and "reply" in response.lower():
                await self.dictate_reply(m)

            # "next", silence, or unrecognised → advance

        self._current_message = None
        await self._tts.speak("End of inbox.", priority="normal")

    async def _read_full_body(self, msg) -> None:
        """Fetch and speak the complete body of an email message."""
        await self._tts.speak("Fetching full message. Please wait.", priority="normal")
        for client in self._clients:
            fn = getattr(client, "get_message_body", None)
            if fn:
                try:
                    body = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.get_message_body(msg.id)
                    )
                    if body:
                        await self._tts.speak(body, priority="normal")
                        return
                except Exception:
                    log.exception("Failed to fetch full body for message %s", msg.id)
        await self._tts.speak("Could not fetch the full message body.", priority="normal")

    async def read_current_full(self) -> None:
        """Read the full body of the currently navigated message (if any)."""
        if self._current_message:
            await self._read_full_body(self._current_message)
        else:
            await self._tts.speak(
                "No message is currently selected. Open your inbox first.",
                priority="normal",
            )

    async def search_contacts(self, query: str) -> None:
        """Search and speak contact details for a name or email."""
        await self._tts.speak(f"Searching for {query}.", priority="normal")
        for client in self._clients:
            fn = getattr(client, "search_contacts", None)
            if fn:
                try:
                    results = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.search_contacts(query)
                    )
                    if not results:
                        await self._tts.speak(f"No contacts found for {query}.", priority="normal")
                        return
                    for person in results:
                        parts = [person["displayName"]]
                        if person.get("jobTitle"):
                            parts.append(person["jobTitle"])
                        if person.get("department"):
                            parts.append(person["department"])
                        if person.get("emailAddress"):
                            parts.append(f"Email: {person['emailAddress']}")
                        if person.get("phone"):
                            parts.append(f"Phone: {person['phone']}")
                        await self._tts.speak(". ".join(parts) + ".", priority="normal")
                    return
                except Exception:
                    log.exception("Contact search failed")
        await self._tts.speak("Contact search is not available.", priority="normal")

    # ------------------------------------------------------------------
    # Teams chat messages
    # ------------------------------------------------------------------

    async def announce_chats(self) -> None:
        """Read out recent Teams chat messages with 'next' / 'stop' navigation."""
        messages = await self._fetch_chats(5)

        if not messages:
            await self._tts.speak("No recent Teams messages.", priority="normal")
            return

        count = len(messages)
        await self._tts.speak(
            f"{count} recent Teams message{'s' if count != 1 else ''}. "
            "Say next after each, or stop to exit.",
            priority="normal",
        )

        for i, m in enumerate(messages):
            chat_label = f"in {m.chat_topic}" if m.chat_topic else "in a chat"
            await self._tts.speak(
                f"Message {i + 1} of {count}. "
                f"From {m.sender_name} {chat_label}. "
                f"{m.content_preview}",
                priority="normal",
            )
            if i < count - 1:
                await self._tts.speak("Say next or stop.", priority="normal")
                response = await self._listen_brief()
                if _is_stop_command(response):
                    await self._tts.speak("Exiting messages.", priority="normal")
                    return

        await self._tts.speak("End of Teams messages.", priority="normal")

    # ------------------------------------------------------------------
    # "What did I miss?" — recent email summary
    # ------------------------------------------------------------------

    async def what_did_i_miss(
        self,
        upcoming_meetings: list | None = None,
        missed_calls_summary: str = "",
    ) -> None:
        """Summarise missed calls, emails from the last hour, and upcoming meetings."""
        recent: list = []
        for client in self._clients:
            fn = getattr(client, "recent_messages", None)
            if fn:
                try:
                    msgs = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.recent_messages(1)
                    )
                    recent.extend(msgs)
                except Exception:
                    log.exception("Failed to fetch recent messages from %s", type(client).__name__)

        recent.sort(key=lambda m: m.received_at, reverse=True)

        if not recent:
            email_part = "No new emails in the last hour."
        elif len(recent) == 1:
            m = recent[0]
            priority_tag = "High priority. " if self._is_high_priority(m) else ""
            email_part = f"1 new email. {priority_tag}From {m.sender_name}. Subject: {m.subject}."
        else:
            high = sum(1 for m in recent if self._is_high_priority(m))
            email_part = f"{len(recent)} new emails in the last hour."
            if high:
                email_part += f" {high} high priority."
            email_part += " Press Control Shift F2 to read them."

        if upcoming_meetings:
            mtg = upcoming_meetings[0]
            from datetime import timezone as _tz
            from datetime import datetime as _dt
            mins = int((mtg.start - _dt.now(_tz.utc)).total_seconds() / 60)
            platform_name = (mtg.platform or "meeting").replace("_", " ").title()
            mtg_part = (
                f"Your next meeting is {platform_name}: {mtg.subject}, "
                f"starting in {mins} minute{'s' if mins != 1 else ''}."
            )
        else:
            mtg_part = "No upcoming meetings in the next hour."

        # Lead with missed calls if any — most time-sensitive item
        calls_part = f"{missed_calls_summary} " if missed_calls_summary else ""

        await self._tts.speak(
            f"Here is what you missed. {calls_part}{email_part} {mtg_part}",
            priority="normal",
        )

    # ------------------------------------------------------------------
    # OneNote dictation
    # ------------------------------------------------------------------

    async def create_note(self) -> None:
        """Dictate a note and save it to OneNote via the Graph API."""
        await self._tts.speak(
            "Creating a note. Say the title, or say skip for today's date.",
            priority="normal",
        )
        await asyncio.sleep(0.2)
        title_resp = await self._stt.listen_once()

        if not title_resp or "skip" in title_resp.lower():
            from datetime import datetime
            title = datetime.now().strftime("Quick Note %B %d %Y")
        else:
            title = title_resp.strip()

        await self._tts.speak(
            f"Title: {title}. Speak your note. Say done when finished.",
            priority="normal",
        )
        content = await self._collect_dictation()

        if not content:
            await self._tts.speak("No content captured. Note cancelled.", priority="normal")
            return

        await self._tts.speak(
            f"Saving note: {title}.",
            priority="normal",
        )

        saved = False
        for client in self._clients:
            fn = getattr(client, "create_note", None)
            if fn:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.create_note(title, content)
                    )
                    saved = True
                    break
                except Exception:
                    log.exception("Failed to create OneNote page")

        if saved:
            await self._tts.speak("Note saved to OneNote.", priority="normal")
        else:
            await self._tts.speak(
                "Could not save the note. Microsoft 365 may not be connected.",
                priority="normal",
            )

    # ------------------------------------------------------------------
    # Dictation reply
    # ------------------------------------------------------------------

    async def dictate_reply(self, original_message) -> None:
        await self._tts.speak(
            f"Dictating reply to {original_message.sender_name}. "
            "Speak your message. Say done when finished.",
            priority="normal",
        )
        body = await self._collect_dictation()
        if not body:
            await self._tts.speak("No message captured. Reply cancelled.", priority="alert")
            return

        await self._tts.speak(
            f"I will send the following reply to {original_message.sender_name}. "
            f"Message: {body}",
            priority="alert",
        )

        async def send_it() -> None:
            client = self._clients[0]
            send_fn = getattr(client, "send_email", None) or getattr(client, "send_message", None)
            if not send_fn:
                await self._tts.speak("Send not available — email client has no send method.", priority="normal")
                return
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: send_fn(
                    original_message.sender_email,
                    f"Re: {original_message.subject}",
                    body,
                ),
            )
            await self._tts.speak("Reply sent.", priority="normal")

        await self._fsm.request(ConsentRequest(
            notification=f"Ready to send reply to {original_message.sender_name}.",
            query="Ready to send?",
            action=send_it,
            action_label=f"send_reply_{original_message.id[:8]}",
        ))

    async def compose_wizard(self) -> None:
        """
        Guided step-by-step compose flow.
        Prompts for recipient, subject, and body in sequence.
        After body dictation, reads the full draft back and lets the user
        say send, re-dictate (redo body only), or cancel.
        """
        # ── Step 1: Recipient ──────────────────────────────────────────────
        await self._tts.speak("Who do you want to send to?", priority="alert")
        await asyncio.sleep(PRE_LISTEN_SETTLE_SECS)
        name_raw = await self._stt.listen_once()
        if not name_raw or _is_stop_command(name_raw):
            await self._tts.speak("Compose cancelled.", priority="normal")
            return

        # ── Step 2: Contact resolution ─────────────────────────────────────
        display_name, email_addr = await self._resolve_contact(name_raw.strip())
        if not display_name:
            await self._tts.speak(
                f"No contact found for {name_raw.strip()}. Compose cancelled.",
                priority="normal",
            )
            return

        # ── Step 3: Subject ────────────────────────────────────────────────
        await self._tts.speak(
            f"Sending to {display_name}. What is the subject?", priority="normal"
        )
        await asyncio.sleep(PRE_LISTEN_SETTLE_SECS)
        subject_raw = await self._stt.listen_once()
        if not subject_raw or _is_stop_command(subject_raw):
            await self._tts.speak("Compose cancelled.", priority="normal")
            return
        subject = subject_raw.strip()

        # ── Steps 4 + 5: Body dictation with re-dictate loop ──────────────
        while True:
            await self._tts.speak(
                "Speak your message. Say done when finished.", priority="normal"
            )
            body = await self._collect_dictation()
            if not body:
                await self._tts.speak(
                    "No message captured. Compose cancelled.", priority="normal"
                )
                return

            preview = body[:200] + ("..." if len(body) > 200 else "")
            await self._tts.speak(
                f"To: {display_name}. Subject: {subject}. Message: {preview}. "
                "Say send, save draft, re-dictate, or cancel.",
                priority="alert",
            )
            await asyncio.sleep(PRE_LISTEN_SETTLE_SECS)
            decision = await self._stt.listen_once()
            if not decision:
                await self._tts.speak("No response. Compose cancelled.", priority="normal")
                return

            d = decision.strip().lower()
            if _is_stop_command(decision) or "cancel" in d or "abort" in d:
                await self._tts.speak("Compose cancelled.", priority="normal")
                return
            if any(w in d for w in ("re-dictate", "redo", "again", "rewrite", "change")):
                continue  # loop back to body dictation
            if any(w in d for w in ("draft", "save", "keep")):
                await self._save_draft(email_addr, subject, body, display_name)
                return
            break  # "send", "yes", "ok", "confirm", or anything else → proceed

        # ── Step 6: Send ───────────────────────────────────────────────────
        client = self._clients[0] if self._clients else None
        send_fn = (
            (getattr(client, "send_email", None) or getattr(client, "send_message", None))
            if client else None
        )
        if not send_fn:
            await self._tts.speak(
                "Send is not available. Microsoft 365 may not be connected.",
                priority="normal",
            )
            return

        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: send_fn(email_addr, subject, body)
            )
            await self._tts.speak(f"Email sent to {display_name}.", priority="normal")
        except Exception:
            log.exception("compose_wizard: send failed to %s", email_addr)
            await self._tts.speak(
                "Send failed. Please check your connection and try again.",
                priority="normal",
            )

    async def _resolve_contact(self, name: str) -> tuple[str, str]:
        """
        Search contacts by name. Returns (display_name, email_address).
        If two matches are found, speaks both and asks 'first or second'.
        Returns ("", "") when nothing is found or the user does not choose.
        """
        results: list = []
        for client in self._clients:
            fn = getattr(client, "search_contacts", None)
            if fn:
                try:
                    found = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.search_contacts(name)
                    )
                    if found:
                        results = found
                        break
                except Exception:
                    log.exception("compose_wizard: contact search failed")

        if not results:
            return ("", "")

        if len(results) == 1:
            r = results[0]
            return (r.get("displayName", name), r.get("emailAddress", ""))

        top = results[:2]
        labels = []
        for r in top:
            label = r.get("displayName", "Unknown")
            if r.get("department"):
                label += f" from {r['department']}"
            labels.append(label)

        await self._tts.speak(
            f"Two contacts found. {labels[0]}, or {labels[1]}. Say first or second.",
            priority="normal",
        )
        await asyncio.sleep(PRE_LISTEN_SETTLE_SECS)
        choice = await self._stt.listen_once()
        if not choice:
            return ("", "")

        idx = 1 if ("second" in choice.lower() or "2" in choice) else 0
        r = top[idx]
        return (r.get("displayName", name), r.get("emailAddress", ""))

    async def _save_draft(
        self, email_addr: str, subject: str, body: str, display_name: str
    ) -> None:
        client = self._clients[0] if self._clients else None
        draft_fn = getattr(client, "save_draft", None) if client else None
        if not draft_fn:
            await self._tts.speak(
                "Save draft is not available. Microsoft 365 may not be connected.",
                priority="normal",
            )
            return
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: draft_fn(email_addr, subject, body)
            )
            await self._tts.speak(
                f"Draft saved. You can find it in your Drafts folder in Outlook.",
                priority="normal",
            )
        except Exception:
            log.exception("_save_draft: failed for %s", email_addr)
            await self._tts.speak(
                "Could not save the draft. Please check your connection.",
                priority="normal",
            )

    async def compose_new(self, to: str, subject: str) -> None:
        await self._tts.speak(
            f"Composing new email to {to}. Subject: {subject}. "
            "Speak your message. Say done when finished.",
            priority="normal",
        )
        body = await self._collect_dictation()
        if not body:
            await self._tts.speak("No message captured. Cancelled.", priority="alert")
            return

        await self._tts.speak(
            f"New email to {to}. Subject: {subject}. Message: {body}",
            priority="alert",
        )

        async def send_it() -> None:
            client = self._clients[0]
            send_fn = getattr(client, "send_email", None) or getattr(client, "send_message", None)
            if not send_fn:
                await self._tts.speak("Send not available — email client has no send method.", priority="normal")
                return
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: send_fn(to, subject, body)
            )
            await self._tts.speak("Email sent.", priority="normal")

        await self._fsm.request(ConsentRequest(
            notification=f"Ready to send new email to {to}.",
            query="Ready to send?",
            action=send_it,
            action_label=f"send_new_to_{to[:20]}",
        ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _collect_dictation(self) -> str:
        parts: list[str] = []
        while True:
            chunk = await self._stt.listen_once()
            if not chunk:
                break
            if chunk.strip().lower() in {"done", "finished", "end", "stop", "send it"}:
                break
            parts.append(chunk.strip())
        return " ".join(parts)

    async def _listen_brief(self) -> str:
        """
        Short listen for navigation commands ('next', 'stop').
        Uses listen_command() which has tight VAD settings (finishes in ~4 s
        naturally) — avoids the asyncio.wait_for executor-cancellation race
        that previously orphaned the recording thread and broke 'stop'.
        A small settle delay lets audio ring-out clear before the mic opens.
        """
        await asyncio.sleep(PRE_LISTEN_SETTLE_SECS)
        listen_fn = getattr(self._stt, "listen_command", self._stt.listen_once)
        return await listen_fn()

    async def _latest_in_thread(self, msg) -> object | None:
        """Return the most recent message in msg's conversation thread, or None."""
        conv_id = getattr(msg, "conversation_id", "")
        if not conv_id:
            return None
        for client in self._clients:
            fn = getattr(client, "latest_in_thread", None)
            if fn:
                try:
                    return await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.latest_in_thread(conv_id)
                    )
                except Exception:
                    log.exception("Failed to fetch thread for conversation %s", conv_id)
        return None

    async def _fetch_chats(self, count: int) -> list:
        """Fetch recent Teams chat messages from all clients that support it."""
        all_messages = []
        for client in self._clients:
            fn = getattr(client, "unread_chats", None)
            if fn:
                try:
                    msgs = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.unread_chats(count)
                    )
                    all_messages.extend(msgs)
                except Exception:
                    log.exception("Failed to fetch chats from %s", type(client).__name__)
        all_messages.sort(key=lambda m: m.received_at, reverse=True)
        return all_messages[:count]

    async def _fetch_unread(self, count: int) -> list:
        all_messages = []
        for client in self._clients:
            try:
                msgs = await asyncio.get_running_loop().run_in_executor(
                    None, lambda c=client: c.unread_messages(count)
                )
                all_messages.extend(msgs)
            except Exception:
                log.exception("Failed to fetch messages from %s", type(client).__name__)
        all_messages.sort(key=lambda m: m.received_at, reverse=True)
        return all_messages[:count]

    async def _fetch_delta(
        self, delta_link: str | None, count: int = 20
    ) -> tuple[list, str | None]:
        """
        Use Graph $delta if any client supports it; fall back to unread_messages.
        Returns (messages, new_delta_link).
        """
        for client in self._clients:
            fn = getattr(client, "delta_inbox_messages", None)
            if fn:
                try:
                    msgs, new_link = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.delta_inbox_messages(delta_link, count)
                    )
                    return msgs, new_link
                except Exception:
                    log.exception("delta_inbox_messages failed on %s", type(client).__name__)
        # Fallback: plain unread fetch, no delta link
        msgs = await self._fetch_unread(count)
        return msgs, None

    async def _fetch_new_since_seed(self) -> list:
        """
        Incremental poll: use delta link when available; fall back to full fetch.
        Updates _seen_ids and _email_delta_link in place.
        """
        msgs, new_link = await self._fetch_delta(self._email_delta_link, count=20)
        if new_link:
            self._email_delta_link = new_link
        elif self._email_delta_link:
            # delta link expired (410) — re-seed on next call
            log.warning("Email delta link expired; re-seeding next cycle")
            self._email_delta_link = None

        new = [m for m in msgs if m.id not in self._seen_ids]
        for m in new:
            self._seen_ids.add(m.id)
        return new

    @staticmethod
    def _is_high_priority(msg) -> bool:
        if getattr(msg, "is_high_priority", False) or getattr(msg, "is_important", False):
            return True
        text = (
            msg.subject + " "
            + getattr(msg, "preview", "")
            + getattr(msg, "snippet", "")
        ).lower()
        return any(kw in text for kw in HIGH_PRIORITY_KEYWORDS)
