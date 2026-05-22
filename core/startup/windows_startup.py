"""
Windows startup registration — adds/removes Lightworks Pro from the
HKCU Run key so it launches automatically at user login.

Uses HKCU (current user) so no admin rights are required.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_RUN_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "LightworksPro"


def is_registered() -> bool:
    """Return True if Lightworks Pro is set to run at Windows startup."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False


def register(exe_path: Optional[Path] = None) -> None:
    """Add Lightworks Pro to Windows startup for the current user."""
    import winreg
    path = exe_path or _resolve_exe_path()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                        access=winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, str(path))
    log.info("Registered startup: %s", path)


def unregister() -> None:
    """Remove Lightworks Pro from Windows startup."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                            access=winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _APP_NAME)
        log.info("Unregistered startup")
    except FileNotFoundError:
        pass


def _resolve_exe_path() -> Path:
    """Return the path to the running executable (handles both dev and frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    # Development mode — point to the __main__.py launcher
    return Path(sys.executable).parent / "python.exe"


# ------------------------------------------------------------------
# AppData config directory
# ------------------------------------------------------------------

def app_data_dir() -> Path:
    """Return %APPDATA%\\LightworksPro, creating it if needed."""
    import os
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    d = base / "LightworksPro"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_data_dir() / "config.json"


def log_path() -> Path:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "lightworks_pro.log"
