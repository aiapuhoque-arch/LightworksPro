"""
Lightworks Pro — Windows entry point.

Behaviour varies by context:
  Installed (frozen exe) : config in %APPDATA%\\LightworksPro\\config.json
  Development (python)   : config in the project root config.json

Special arguments:
  --quit        : signal a running instance to exit (used by uninstaller)
  --setup       : force-run the first-run setup wizard
  --log-level X : override log level
"""
from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
from pathlib import Path


def _resolve_config_path(cli_config: str | None) -> Path:
    """
    Installed exe → %APPDATA%\\LightworksPro\\config.json
    Dev / explicit → argument or project root config.json
    """
    if cli_config:
        return Path(cli_config)
    if getattr(sys, "frozen", False):
        from core.startup.windows_startup import config_path
        return config_path()
    return Path(__file__).parent / "config.json"


def _setup_logging(level: str, frozen: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if frozen:
        from core.startup.windows_startup import log_path
        fh = logging.FileHandler(log_path(), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        handlers.append(fh)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def _signal_quit() -> None:
    """Send a quit signal to the running instance via a sentinel file, then exit."""
    from core.startup.windows_startup import app_data_dir
    sentinel = app_data_dir() / ".quit"
    sentinel.touch()
    sys.exit(0)


def main() -> None:
    # Patch SSL to use Windows native certificate store so corporate CA certs
    # (Zscaler, etc.) are trusted without manual bundle configuration.
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass  # falls back to certifi if truststore not installed or fails

    parser = argparse.ArgumentParser(description="Lightworks Pro Voice Assistant")
    parser.add_argument("--config",     default=None,    help="Path to config.json")
    parser.add_argument("--log-level",  default=None,    help="Override log level")
    parser.add_argument("--setup",      action="store_true", help="Re-run setup wizard")
    parser.add_argument("--quit",       action="store_true", help="Signal running instance to quit")
    args = parser.parse_args()

    frozen = getattr(sys, "frozen", False)

    if args.quit:
        _signal_quit()
        return

    _setup_logging(args.log_level or "INFO", frozen)
    log = logging.getLogger(__name__)
    log.info("Lightworks Pro starting (frozen=%s, python=%s)", frozen, sys.version.split()[0])

    if platform.system() != "Windows":
        print(f"Platform '{platform.system()}' is not yet supported. Windows only in Phase 1.")
        sys.exit(1)

    cfg_path = _resolve_config_path(args.config)
    first_run = not cfg_path.exists() or args.setup

    if first_run:
        import asyncio
        from core.setup_wizard.wizard import SetupWizard
        log.info("First run detected — launching setup wizard")
        config = asyncio.run(SetupWizard().run())
    else:
        with open(cfg_path, encoding="utf-8") as f:
            config = json.load(f)
        log_level = args.log_level or config.get("log_level", "INFO")
        logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Watch for quit sentinel (uninstaller sends this)
    _start_quit_watcher(cfg_path.parent if frozen else None)

    from desktop.windows.tray_service import WindowsTrayService
    WindowsTrayService(config).start()


def _start_quit_watcher(app_data: Path | None) -> None:
    """Poll for a .quit sentinel file so the uninstaller can cleanly stop the app."""
    if not app_data:
        return
    import threading, time

    sentinel = app_data / ".quit"

    def watch() -> None:
        while True:
            time.sleep(2)
            if sentinel.exists():
                sentinel.unlink(missing_ok=True)
                logging.getLogger(__name__).info("Quit sentinel detected — shutting down")
                # pystray icon stop must happen on the icon's own thread;
                # setting a module-level flag is the cleanest cross-thread signal.
                import desktop.windows.tray_service as svc
                if svc._active_service:
                    svc._active_service._on_quit()
                break

    threading.Thread(target=watch, daemon=True, name="lw-quit-watch").start()


if __name__ == "__main__":
    main()
