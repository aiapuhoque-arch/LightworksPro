"""
System status utilities for Lightworks Pro.

All functions are synchronous and safe to call from a thread-pool executor.
No network access — purely local OS queries.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── NATO phonetic alphabet ────────────────────────────────────────────────────
_NATO = {
    "a": "Alpha",   "b": "Bravo",   "c": "Charlie", "d": "Delta",
    "e": "Echo",    "f": "Foxtrot", "g": "Golf",    "h": "Hotel",
    "i": "India",   "j": "Juliet",  "k": "Kilo",    "l": "Lima",
    "m": "Mike",    "n": "November","o": "Oscar",   "p": "Papa",
    "q": "Quebec",  "r": "Romeo",   "s": "Sierra",  "t": "Tango",
    "u": "Uniform", "v": "Victor",  "w": "Whiskey", "x": "X-ray",
    "y": "Yankee",  "z": "Zulu",
    "0": "Zero",    "1": "One",     "2": "Two",     "3": "Three",
    "4": "Four",    "5": "Five",    "6": "Six",     "7": "Seven",
    "8": "Eight",   "9": "Nine",
}

# Known screen reader process names
_SCREEN_READERS = {
    "JAWS":       "jfw.exe",
    "NVDA":       "nvda.exe",
    "SuperNova":  "supernova.exe",
    "ZoomText":   "zoomtext.exe",
    "Narrator":   "narrator.exe",
}


# ------------------------------------------------------------------
# Clipboard
# ------------------------------------------------------------------

def read_clipboard() -> str:
    """Return text currently on the Windows clipboard, or empty string."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return (text or "").strip()
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:
        log.warning("Could not read clipboard: %s", e)
    return ""


# ------------------------------------------------------------------
# Time and date
# ------------------------------------------------------------------

def get_time_spoken() -> str:
    """Return current local time as a spoken string, e.g. '2:45 PM'."""
    now = datetime.now()
    return now.strftime("%I:%M %p").lstrip("0")


def get_date_spoken() -> str:
    """Return today's date as a spoken string, e.g. 'Thursday, May 7th, 2026'."""
    now = datetime.now()
    day = now.day
    suffix = (
        "th" if 11 <= day <= 13
        else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    )
    return now.strftime(f"%A, %B {day}{suffix}, %Y")


# ------------------------------------------------------------------
# Battery
# ------------------------------------------------------------------

def get_battery_status() -> str:
    """Return a spoken battery status string."""
    try:
        import psutil
        batt = psutil.sensors_battery()
        if batt is None:
            return "No battery detected. This device appears to be desktop or always plugged in."
        percent = int(batt.percent)
        if batt.power_plugged:
            if percent >= 100:
                status = "fully charged"
            else:
                status = "charging"
        else:
            if percent <= 10:
                status = "critically low — please plug in now"
            elif percent <= 20:
                status = "low"
            else:
                status = "on battery power"

        secs_left = batt.secsleft
        if secs_left and secs_left > 0 and not batt.power_plugged:
            hours, mins = divmod(secs_left // 60, 60)
            if hours > 0:
                time_left = f" Estimated {hours} hour{'s' if hours != 1 else ''}"
                if mins:
                    time_left += f" and {mins} minute{'s' if mins != 1 else ''}"
                time_left += " remaining."
            else:
                time_left = f" Estimated {mins} minute{'s' if mins != 1 else ''} remaining."
        else:
            time_left = ""

        return f"Battery is at {percent} percent, {status}.{time_left}"
    except ImportError:
        return "Battery status unavailable. The psutil library is not installed."
    except Exception as e:
        log.warning("Battery query failed: %s", e)
        return "Could not read battery status."


# ------------------------------------------------------------------
# Active window — "Where am I?"
# ------------------------------------------------------------------

def get_foreground_window_info() -> str:
    """Return a spoken description of the current foreground window."""
    try:
        import win32gui
        import win32process
        import psutil

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "No active window found."

        title = win32gui.GetWindowText(hwnd).strip()

        # Get process name from PID
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            app_name = proc.name().replace(".exe", "").replace("-", " ").title()
        except Exception:
            app_name = "Unknown application"

        if title:
            return f"You are in {app_name}. Window title: {title}."
        return f"You are in {app_name}."

    except ImportError:
        return "Active window detection requires psutil. Please install it."
    except Exception as e:
        log.warning("Foreground window query failed: %s", e)
        return "Could not determine the active window."


# ------------------------------------------------------------------
# Recent files
# ------------------------------------------------------------------

def get_recent_files(count: int = 5) -> list[str]:
    """
    Return the names (without extension) of the most recently accessed files
    from the Windows Recent Items folder. Returns display-ready names only.
    """
    try:
        recent_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
        if not recent_dir.exists():
            return []
        lnk_files = sorted(
            recent_dir.glob("*.lnk"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        names: list[str] = []
        for lnk in lnk_files:
            name = lnk.stem   # filename without .lnk
            # Skip system/temp entries
            if name.startswith("~") or name.startswith("."):
                continue
            names.append(name)
            if len(names) >= count:
                break
        return names
    except Exception as e:
        log.warning("Recent files query failed: %s", e)
        return []


def open_recent_file(name_fragment: str) -> bool:
    """
    Find the most recent file whose name contains name_fragment (case-insensitive)
    and open it with its default handler. Returns True if found and launched.
    """
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        recent_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
        fragment = name_fragment.lower()
        candidates = sorted(
            [p for p in recent_dir.glob("*.lnk") if fragment in p.stem.lower()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return False
        shortcut = shell.CreateShortcut(str(candidates[0]))
        target = shortcut.Targetpath
        if target and Path(target).exists():
            os.startfile(target)
            return True
        return False
    except Exception as e:
        log.warning("Could not open recent file '%s': %s", name_fragment, e)
        return False


# ------------------------------------------------------------------
# Screen reader detection
# ------------------------------------------------------------------

def detect_screen_readers() -> list[str]:
    """Return names of running screen readers (e.g. ['JAWS', 'NVDA'])."""
    try:
        import psutil
        running_names = {p.info["name"].lower() for p in psutil.process_iter(["name"])}
        return [
            name for name, exe in _SCREEN_READERS.items()
            if exe.lower() in running_names
        ]
    except ImportError:
        return []
    except Exception as e:
        log.warning("Screen reader detection failed: %s", e)
        return []


# ------------------------------------------------------------------
# Phonetic spelling
# ------------------------------------------------------------------

def phonetic_spell(text: str) -> str:
    """
    Return a spoken phonetic spelling using the NATO alphabet.
    E.g. "AB3" → "A as in Alpha,  B as in Bravo,  3 as in Three."
    Spaces between words are announced as 'space'.
    """
    parts: list[str] = []
    for ch in text:
        if ch == " ":
            parts.append("space")
        elif ch.lower() in _NATO:
            word = _NATO[ch.lower()]
            parts.append(f"{ch.upper()} as in {word}")
        else:
            parts.append(ch)
    return ",  ".join(parts) + "."


# ------------------------------------------------------------------
# Teams / presence status helpers (local descriptions)
# ------------------------------------------------------------------

_PRESENCE_LABELS = {
    "Available":      "available",
    "Busy":           "busy",
    "DoNotDisturb":   "do not disturb",
    "Away":           "away",
    "BeRightBack":    "be right back",
    "Offline":        "offline",
}


def presence_label(availability: str) -> str:
    return _PRESENCE_LABELS.get(availability, availability.lower())
