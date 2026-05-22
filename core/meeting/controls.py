"""
Meeting keyboard controls — sends hotkeys to the active Teams or Zoom window.

Approach: find the app window via win32gui, bring it to the foreground,
send keystrokes via keybd_event, then restore focus to the previous window.
All calls are synchronous — run them in a thread-pool executor from async code.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

import win32api
import win32con
import win32gui

log = logging.getLogger(__name__)

# ── Teams in-meeting shortcuts (Ctrl+Shift+key) ───────────────────────────────
_TEAMS_MUTE   = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("M")]
_TEAMS_LEAVE  = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("H")]
_TEAMS_HAND   = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("K")]
_TEAMS_CAM    = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("O")]

# ── Teams incoming-call shortcuts ─────────────────────────────────────────────
_TEAMS_ACCEPT_AUDIO = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("A")]
_TEAMS_ACCEPT_VIDEO = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("V")]
_TEAMS_DECLINE      = [win32con.VK_CONTROL, win32con.VK_SHIFT, ord("D")]

# ── Zoom shortcuts ────────────────────────────────────────────────────────────
_ZOOM_MUTE    = [win32con.VK_MENU, ord("A")]          # Alt+A
_ZOOM_LEAVE   = [win32con.VK_MENU, ord("Q")]          # Alt+Q
_ZOOM_HAND    = [win32con.VK_MENU, ord("Y")]          # Alt+Y
_ZOOM_CAM     = [win32con.VK_MENU, ord("V")]          # Alt+V
_ZOOM_ACCEPT  = [win32con.VK_MENU, ord("A")]          # same as unmute — accept in incoming screen

_WINDOW_TITLES = {
    # Classic Teams: "Microsoft Teams"; new Teams 2024: same title, different exe (ms-teams.exe)
    "teams": ["microsoft teams", "teams"],
    "zoom":  ["zoom meeting", "zoom"],
}

# Window title fragments that signal an incoming call notification.
# New Teams 2024 popup titles may use "is calling" or "calling you" without "incoming".
_INCOMING_CALL_TITLES = [
    "incoming call",
    "incoming video call",
    "is calling",
    "calling you",
    "audio call",
]


def _find_window(platform: str) -> int | None:
    """Return HWND of the first visible window matching the platform."""
    keywords = _WINDOW_TITLES.get(platform, [])
    found: list[int] = []

    def _cb(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).lower()
        if any(kw in title for kw in keywords):
            found.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def _send(platform: str, vk_list: list[int]) -> bool:
    """Find the platform window and send a key combo to it."""
    hwnd = _find_window(platform)
    if not hwnd:
        log.warning("Meeting window not found for platform=%s", platform)
        return False
    return _send_to_hwnd(hwnd, vk_list)


def mute_toggle(platform: str = "teams") -> bool:
    keys = _TEAMS_MUTE if platform == "teams" else _ZOOM_MUTE
    return _send(platform, keys)


def leave_meeting(platform: str = "teams") -> bool:
    keys = _TEAMS_LEAVE if platform == "teams" else _ZOOM_LEAVE
    return _send(platform, keys)


def raise_hand(platform: str = "teams") -> bool:
    keys = _TEAMS_HAND if platform == "teams" else _ZOOM_HAND
    return _send(platform, keys)


def camera_toggle(platform: str = "teams") -> bool:
    keys = _TEAMS_CAM if platform == "teams" else _ZOOM_CAM
    return _send(platform, keys)


def answer_call(platform: str = "teams", with_video: bool = False) -> bool:
    """Answer an incoming Teams/Zoom call."""
    if platform == "teams":
        keys = _TEAMS_ACCEPT_VIDEO if with_video else _TEAMS_ACCEPT_AUDIO
    else:
        keys = _ZOOM_ACCEPT
    # For incoming calls the notification window may be separate — try both
    hwnd = _find_window(platform)
    if not hwnd:
        # Teams incoming call may have its own small window
        hwnd = _find_incoming_call_window()
    if not hwnd:
        return False
    return _send_to_hwnd(hwnd, keys)


def decline_call(platform: str = "teams") -> bool:
    """Decline an incoming Teams call."""
    keys = _TEAMS_DECLINE
    hwnd = _find_window(platform) or _find_incoming_call_window()
    if not hwnd:
        return False
    return _send_to_hwnd(hwnd, keys)


def find_incoming_call_info() -> Optional[tuple[str, str]]:
    """
    Scan all visible windows for an incoming call notification.
    Returns (caller_name, platform) if found, else None.
    Teams shows a small overlay window titled "Incoming call — [Name]".
    """
    results: list[tuple[str, str]] = []

    def _cb(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).lower()
        if any(frag in title for frag in _INCOMING_CALL_TITLES):
            # Extract caller name — Teams format: "Incoming call — Name"
            raw = win32gui.GetWindowText(hwnd)
            for sep in (" — ", " - ", ": ", " from "):
                if sep.lower() in raw.lower():
                    idx = raw.lower().index(sep.lower())
                    caller = raw[idx + len(sep):].strip()
                    results.append((caller, "teams"))
                    return
            results.append((raw.strip(), "teams"))

    win32gui.EnumWindows(_cb, None)
    return results[0] if results else None


def is_app_open(platform: str) -> bool:
    return _find_window(platform) is not None


def _uia_click_button(names: list[str], timeout: float, hwnd: int = 0) -> bool:
    """
    Poll the UI tree for any button matching `names` and click it.

    Pass 1 — exact UIA Name match (fast FindFirst per name).
    Pass 2 — whole-word regex match across ALL buttons: catches Electron buttons
             whose accessible name includes extra context, e.g.
             "Call +1 646 255 6312" or "Audio call John Smith".
    Click strategy per element: UIA Invoke → mouse click at centre.

    hwnd — if non-zero, scope the search to that specific window handle instead of
           the full desktop.  Scoping to the call dialog window prevents accidentally
           clicking Teams sidebar navigation buttons (e.g. "Calls") that are also
           present in the UIA tree.
    """
    try:
        import comtypes.client as cc
        cc.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import (  # type: ignore[import]
            CUIAutomation8, IUIAutomation, IUIAutomationInvokePattern,
            TreeScope_Descendants, UIA_NamePropertyId, UIA_InvokePatternId,
            UIA_ControlTypePropertyId,
        )
        UIA_ButtonControlTypeId = 50000

        uia: IUIAutomation = cc.CreateObject(CUIAutomation8, interface=IUIAutomation)
        root = uia.ElementFromHandle(hwnd) if hwnd else uia.GetRootElement()
        names_lower = [n.lower() for n in names]

        def _click(el) -> bool:
            """UIA Invoke → mouse click."""
            try:
                pattern = el.GetCurrentPattern(UIA_InvokePatternId)
                invoke  = pattern.QueryInterface(IUIAutomationInvokePattern)
                invoke.Invoke()
                return True
            except Exception:
                pass
            try:
                rect = el.CurrentBoundingRectangle
                cx   = (rect.left + rect.right)  // 2
                cy   = (rect.top  + rect.bottom) // 2
                win32api.SetCursorPos((cx, cy))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.05)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)
                return True
            except Exception as e:
                log.debug("Mouse click failed: %s", e)
                return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            # ── Pass 1: exact match (one FindFirst per name, very fast) ──
            for name in names:
                cond = uia.CreatePropertyCondition(UIA_NamePropertyId, name)
                el   = root.FindFirst(TreeScope_Descendants, cond)
                if el is not None:
                    if _click(el):
                        log.info("UIA click %r (exact match)", name)
                        return True

            # ── Pass 2: whole-word match across all buttons ───────────────
            # Needed when Teams appends context to the button name, e.g.
            # "Call +1 646 255 6312" instead of just "Call".
            # Uses word-boundary regex so "call" does NOT match "calls"
            # (the Teams sidebar nav item), preventing accidental navigation.
            try:
                btn_cond = uia.CreatePropertyCondition(
                    UIA_ControlTypePropertyId, UIA_ButtonControlTypeId
                )
                all_btns = root.FindAll(TreeScope_Descendants, btn_cond)
                if all_btns:
                    for i in range(min(all_btns.Length, 40)):
                        btn = all_btns.GetElement(i)
                        try:
                            btn_name = (btn.CurrentName or "").lower()
                            matched_term = next(
                                (t for t in names_lower
                                 if re.search(r"\b" + re.escape(t) + r"\b", btn_name)),
                                None,
                            )
                            if matched_term and _click(btn):
                                log.info("UIA click (word-match %r in %r)", matched_term, btn_name)
                                return True
                        except Exception:
                            continue
            except Exception:
                pass

            time.sleep(0.4)

        return False
    except Exception as e:
        log.debug("_uia_click_button failed: %s", e)
        return False


def click_teams_join_now(timeout: float = 20.0) -> bool:
    """
    After opening a Teams meeting URL, Teams shows a pre-join lobby with
    a 'Join now' button. Polls for it and clicks via UIA Invoke or mouse.
    Button label varies by Teams version: 'Join now', 'Join', 'Join meeting'.
    """
    ok = _uia_click_button(
        ["Join now", "Join Now", "Join", "Join meeting", "Join the meeting"],
        timeout=timeout,
    )
    if not ok:
        log.warning("Teams 'Join now' button not found within %.0fs", timeout)
    return ok


def dial_teams(users: list[str], with_video: bool = False, display_name: str = "") -> bool:
    """
    Initiate a Teams call via URI.

    URI routing (all schemes registered in Teams' MSIX manifest):
      - PSTN full number (+E.164) : tel:+12125551234  → shows confirmation dialog
      - Extension (short digits)  : callto:1234        → shows confirmation dialog
      - Teams-to-Teams audio      : callto:upn@domain.com   → no dialog, calls directly
      - Teams-to-Teams video      : https://teams.microsoft.com/l/call/0/0?users=upn&withVideo=true
      - Conference (multi-user)   : https://teams.microsoft.com/l/call/0/0?users=a,b

    _confirm_teams_dialog() is called ONLY for PSTN/extension numbers because those are
    the only call types that show "Would you like to call this number?" — email-based
    Teams-to-Teams calls start immediately with no dialog.
    """
    import os
    from urllib.parse import quote

    if not users:
        return False

    def _launch(url: str, *fallbacks: str) -> bool:
        for uri in (url, *fallbacks):
            try:
                os.startfile(uri)
                log.info("Teams dial: %s", uri)
                return True
            except Exception as e:
                log.warning("URI failed (%s): %s", uri, e)
        return False

    import threading as _threading

    def _bg_confirm(wait: float) -> None:
        """Run dialog confirmation in background so dial_teams returns immediately."""
        _confirm_teams_dialog(wait=wait)

    # ── Conference call ───────────────────────────────────────────────────────
    if len(users) > 1:
        encoded = ",".join(quote(u, safe="@:") for u in users)
        suffix  = "&withVideo=true" if with_video else ""
        # msteams:// must come first — os.startfile("https://...") always succeeds
        # by opening the browser, so the Teams-native fallback would never run.
        ok = _launch(
            f"msteams://l/call/0/0?users={encoded}{suffix}",
            f"https://teams.microsoft.com/l/call/0/0?users={encoded}{suffix}",
        )
        if ok:
            _threading.Thread(target=_bg_confirm, args=(6.0,), daemon=True).start()
        return ok

    user = users[0]

    # ── PSTN / extension ─────────────────────────────────────────────────────
    if user.startswith("4:"):
        number = user[2:]
        digit_count = sum(c.isdigit() for c in number)
        is_pstn = number.startswith("+") or digit_count >= 10
        if is_pstn:
            # tel: routes to Teams' native Win32 "Would you like to call?" popup —
            # the same path that works for short extensions.  msteams:// and callto:
            # are fallbacks; callto: is last because it opens Teams' Electron main app
            # rather than the lightweight native dialog.
            ok = _launch(
                f"tel:{number}",
                f"msteams://l/call/0/0?users=4:{quote(number, safe='+')}",
                f"callto:{number}",
            )
            bg_wait = 12.0
        else:
            # Short extension — callto: is Teams' Skype-legacy handler and is
            # more likely to produce a native Win32 dialog than msteams://.
            # tel: is tried second; msteams://...users=4:NNNN is last because
            # it opens Teams Electron (no Win32 dialog, UIA unreliable).
            ok = _launch(
                f"callto:{number}",
                f"tel:{number}",
                f"msteams://l/call/0/0?users=4:{quote(number, safe='')}",
            )
            bg_wait = 5.0
        if ok:
            _threading.Thread(target=_bg_confirm, args=(bg_wait,), daemon=True).start()
        return ok

    # ── Teams-to-Teams (UPN/email-based) ─────────────────────────────────────
    # callto: is tried first — for same-org UPN calls it often opens a lighter
    # Win32-style dialog instead of the full Electron call prep screen, making
    # UIA/keyboard auto-confirm more reliable.  msteams:// is the fallback.
    if with_video:
        ok = _launch(
            f"callto:{user}",
            f"msteams://l/call/0/0?users={quote(user, safe='@:')}&withVideo=true",
            f"https://teams.microsoft.com/l/call/0/0?users={quote(user, safe='@:')}&withVideo=true",
        )
    else:
        ok = _launch(
            f"callto:{user}",
            f"msteams://l/call/0/0?users={quote(user, safe='@:')}",
            f"https://teams.microsoft.com/l/call/0/0?users={quote(user, safe='@:')}",
        )
    if ok:
        # 8 s polling window: callto: dialogs appear quickly; msteams:// Electron
        # screens take longer.  Combined with the 1.5 s pre-wait in
        # _confirm_teams_dialog the total wait is up to 9.5 s.
        _threading.Thread(target=_bg_confirm, args=(8.0,), daemon=True).start()
    return ok


# ── Private helpers ───────────────────────────────────────────────────────────

def _confirm_teams_dialog(wait: float = 8.0) -> None:
    """
    After any Teams call URI fires, Teams may show a confirmation screen
    ('Would you like to call this number?', 'Start a call', etc.).
    Polls for and clicks the primary action button.

    Strategy:
      1. UIA scoped to the call dialog window — prevents hitting Teams sidebar buttons.
      2. UIA full desktop scan — fallback for Electron call-prep screens.
      3. keybd_event Enter/Space — hardware keystroke; works where UIA Invoke fails.
    """
    # Wait for the Teams call dialog to render before scanning.
    time.sleep(1.5)

    _CALL_BTNS = [
        "Call", "Audio call", "Video call", "Start call", "Start a call",
        "Make a call", "Start video call",
    ]

    # After a callto:/tel: URI fires, Teams shows a small confirmation popup that
    # becomes the foreground window.  Scoping UIA to that specific window avoids
    # matching "Calls" (Teams sidebar nav) or calendar "Join now" buttons.
    main_hwnd   = _find_window("teams")
    fg_hwnd     = win32gui.GetForegroundWindow()
    fg_title    = (win32gui.GetWindowText(fg_hwnd) or "").lower()
    dialog_hwnd = 0
    if fg_hwnd and fg_hwnd != main_hwnd and any(
        k in fg_title for k in ("teams", "call", "microsoft")
    ):
        dialog_hwnd = fg_hwnd

    # Pass A — UIA scoped to the call dialog popup (most precise, avoids sidebar hits)
    if dialog_hwnd and _uia_click_button(_CALL_BTNS, timeout=min(wait, 4.0), hwnd=dialog_hwnd):
        return

    # Pass B — full desktop scan (Electron call-prep screen or dialog not yet foreground)
    if _uia_click_button(_CALL_BTNS, timeout=wait):
        return

    log.warning("_confirm_teams_dialog: UIA failed — keyboard fallback")

    target_hwnd = dialog_hwnd or main_hwnd or _find_incoming_call_window()
    if not target_hwnd:
        log.warning("_confirm_teams_dialog: no Teams window for keyboard fallback")
        return
    try:
        _force_foreground(target_hwnd)
        time.sleep(0.7)

        def _press(vk: int) -> None:
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.15)

        # Enter activates the Win32 default button (Call).
        # Space activates the focused Electron button.
        # One Tab in case the button is not the default focused element —
        # intentionally NOT looping to avoid landing on Cancel.
        _press(win32con.VK_RETURN)
        _press(win32con.VK_SPACE)
        _press(win32con.VK_TAB)
        _press(win32con.VK_RETURN)
        _press(win32con.VK_SPACE)
        log.info("Teams dialog: keyboard fallback sent (hwnd=%d)", target_hwnd)
    except Exception as e:
        log.warning("Keyboard fallback failed: %s", e)


def _uia_invoke_button(button_name: str, root_hwnd: int = 0) -> bool:
    """
    Find a button by name via Windows UI Automation and invoke it.
    Uses comtypes (already a project dependency via pycaw).
    Returns True on success. Does not raise — callers should check the return value.

    This method generates NO keyboard events and requires NO window focus change,
    making it fully compatible with JAWS, NVDA, Fusion, and ZoomText.
    """
    try:
        import comtypes.client as cc

        # Load the UIAutomationCore type library (comtypes caches this after first call)
        cc.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import (  # type: ignore[import]
            CUIAutomation8,
            IUIAutomation,
            IUIAutomationInvokePattern,
            TreeScope_Descendants,
            UIA_NamePropertyId,
            UIA_InvokePatternId,
        )

        uia: IUIAutomation = cc.CreateObject(CUIAutomation8, interface=IUIAutomation)

        if root_hwnd:
            root = uia.ElementFromHandle(root_hwnd)
        else:
            root = uia.GetRootElement()

        # Try the requested name first, then common Teams dialog variants
        names_to_try = [button_name, "Start call", "Call anyway", "Accept", "OK"]
        deadline  = time.time() + 3.0
        element   = None
        while time.time() < deadline:
            for name in names_to_try:
                cond = uia.CreatePropertyCondition(UIA_NamePropertyId, name)
                element = root.FindFirst(TreeScope_Descendants, cond)
                if element is not None:
                    log.debug("UIA found button: %r", name)
                    break
            if element is not None:
                break
            time.sleep(0.2)

        if element is None:
            return False

        pattern = element.GetCurrentPattern(UIA_InvokePatternId)
        invoke  = pattern.QueryInterface(IUIAutomationInvokePattern)
        invoke.Invoke()
        return True

    except Exception as e:
        log.debug("UIA invoke failed: %s", e)
        return False


def _force_foreground(hwnd: int) -> None:
    """
    Bring hwnd to foreground reliably using AttachThreadInput.
    Plain SetForegroundWindow is silently blocked by Windows 11 focus-steal
    protection when the calling process does not own the foreground window.
    """
    import ctypes
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    fg = win32gui.GetForegroundWindow()
    if fg == hwnd:
        return
    fg_tid  = ctypes.windll.user32.GetWindowThreadProcessId(fg,   None)
    tgt_tid = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
    if fg_tid and fg_tid != tgt_tid:
        ctypes.windll.user32.AttachThreadInput(fg_tid, tgt_tid, True)
    win32gui.BringWindowToTop(hwnd)
    win32gui.SetForegroundWindow(hwnd)
    if fg_tid and fg_tid != tgt_tid:
        ctypes.windll.user32.AttachThreadInput(fg_tid, tgt_tid, False)
    time.sleep(0.3)


def _find_incoming_call_window() -> Optional[int]:
    """Return HWND of a visible incoming-call notification window, or None."""
    found: list[int] = []

    def _cb(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).lower()
        if any(frag in title for frag in _INCOMING_CALL_TITLES):
            found.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def _send_to_hwnd(hwnd: int, vk_list: list[int]) -> bool:
    """Send a key combo to a specific HWND. Restores previous foreground window."""
    try:
        prev = win32gui.GetForegroundWindow()
        _force_foreground(hwnd)
        time.sleep(0.05)   # _force_foreground already sleeps 0.3 s
        for vk in vk_list:
            win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        for vk in reversed(vk_list):
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)
        if prev and prev != hwnd:
            try:
                win32gui.SetForegroundWindow(prev)
            except Exception:
                pass
        return True
    except Exception as e:
        log.error("Failed to send keys to hwnd=%d: %s", hwnd, e)
        return False
