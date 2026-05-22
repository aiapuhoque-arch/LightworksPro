"""
Microsoft To Do integration via the Graph API.

Supports:
  list_tasks()          — read pending tasks from the default list
  add_task(title)       — create a new task
  complete_task(frag)   — mark the first task whose title contains frag as done
  announce_tasks(tts)   — speak pending tasks with next/stop navigation
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class TodoTask:
    id: str
    list_id: str
    title: str
    importance: str          # "normal" | "high" | "low"
    status: str              # "notStarted" | "inProgress" | "completed"
    due_date: Optional[datetime]


@dataclass
class TodoList:
    id: str
    display_name: str
    is_default: bool


class TodoEngine:
    """
    Thin async wrapper around GraphClient's To Do methods.
    Keeps a cached reference to the default list ID to avoid re-fetching
    on every operation.
    """

    def __init__(self, tts, stt, *graph_clients) -> None:
        self._tts = tts
        self._stt = stt
        self._clients = graph_clients
        self._default_list_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public async API (call from asyncio coroutines)
    # ------------------------------------------------------------------

    async def announce_tasks(self) -> None:
        """Speak pending tasks with 'next' / 'stop' navigation."""
        tasks = await self._fetch_tasks()
        if not tasks:
            await self._tts.speak("Your To Do list is empty.", priority="normal")
            return

        high   = [t for t in tasks if t.importance == "high"]
        normal = [t for t in tasks if t.importance != "high"]
        ordered = high + normal

        count = len(ordered)
        await self._tts.speak(
            f"You have {count} pending task{'s' if count != 1 else ''}."
            + (f" {len(high)} high priority." if high else "")
            + " Say next after each, or stop to exit.",
            priority="normal",
        )

        for i, task in enumerate(ordered):
            priority_tag = "High priority. " if task.importance == "high" else ""
            due_tag = ""
            if task.due_date:
                due_tag = f" Due {_spoken_date(task.due_date)}."
            await self._tts.speak(
                f"Task {i + 1} of {count}. {priority_tag}{task.title}.{due_tag}",
                priority="normal",
            )
            if i < count - 1:
                await self._tts.speak("Say next or stop.", priority="normal")
                await asyncio.sleep(0.2)
                listen_fn = getattr(self._stt, "listen_command", self._stt.listen_once)
                response = await listen_fn()
                if response and any(
                    w in response.lower()
                    for w in ("stop", "done", "exit", "quit", "enough", "no")
                ):
                    await self._tts.speak("Exiting tasks.", priority="normal")
                    return

        await self._tts.speak("End of tasks.", priority="normal")

    async def add_task(self, title: str) -> bool:
        """Create a task in the default To Do list. Returns True on success."""
        list_id = await self._get_default_list_id()
        if not list_id:
            return False
        for client in self._clients:
            fn = getattr(client, "add_todo_task", None)
            if fn:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.add_todo_task(list_id, title)
                    )
                    return True
                except Exception:
                    log.exception("Failed to add task '%s'", title)
        return False

    async def complete_task(self, title_fragment: str) -> Optional[str]:
        """
        Mark the first task whose title contains title_fragment as completed.
        Returns the full task title if found, else None.
        """
        tasks = await self._fetch_tasks()
        frag  = title_fragment.lower()
        match = next((t for t in tasks if frag in t.title.lower()), None)
        if not match:
            return None
        for client in self._clients:
            fn = getattr(client, "complete_todo_task", None)
            if fn:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.complete_todo_task(match.list_id, match.id)
                    )
                    return match.title
                except Exception:
                    log.exception("Failed to complete task '%s'", match.title)
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _fetch_tasks(self) -> list[TodoTask]:
        list_id = await self._get_default_list_id()
        if not list_id:
            return []
        all_tasks: list[TodoTask] = []
        for client in self._clients:
            fn = getattr(client, "get_todo_tasks", None)
            if fn:
                try:
                    tasks = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.get_todo_tasks(list_id)
                    )
                    all_tasks.extend(tasks)
                except Exception:
                    log.exception("Failed to fetch tasks from %s", type(client).__name__)
        return all_tasks

    async def _get_default_list_id(self) -> Optional[str]:
        if self._default_list_id:
            return self._default_list_id
        for client in self._clients:
            fn = getattr(client, "get_todo_lists", None)
            if fn:
                try:
                    lists = await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=client: c.get_todo_lists()
                    )
                    # Prefer the default list; fall back to first
                    default = next((l for l in lists if l.is_default), None) or (lists[0] if lists else None)
                    if default:
                        self._default_list_id = default.id
                        return self._default_list_id
                except Exception:
                    log.exception("Failed to fetch To Do lists from %s", type(client).__name__)
        return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _spoken_date(dt: datetime) -> str:
    """Convert a UTC datetime to a short spoken date like 'May 7th'."""
    local = dt.astimezone()
    day = local.day
    suffix = (
        "th" if 11 <= day <= 13
        else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    )
    return local.strftime(f"%B {day}{suffix}")
