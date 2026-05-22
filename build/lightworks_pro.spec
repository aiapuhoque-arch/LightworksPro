# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Lightworks Pro (Windows x64)
#
# Build with:
#   pyinstaller build/lightworks_pro.spec
#
# Output: dist/LightworksPro/LightworksPro.exe  (onedir mode — faster startup)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent   # project root

block_cipher = None

a = Analysis(
    [str(ROOT / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundled assets
        (str(ROOT / "assets" / "lightworks_pro.ico"), "assets"),
        (str(ROOT / "config.example.json"), "."),
    ],
    hiddenimports=[
        # pyttsx3 SAPI5 driver (Windows TTS)
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",
        # pywin32 / win32com
        "win32api",
        "win32con",
        "win32gui",
        "win32com",
        "win32com.client",
        "win32com.shell",
        "win32com.shell.shell",
        "win32com.shell.shellcon",
        "pythoncom",
        "pywintypes",
        # comtypes (pycaw dependency)
        "comtypes",
        "comtypes.client",
        "comtypes.automation",
        "comtypes.server",
        "comtypes.server.automation",
        "comtypes.typeinfo",
        # keyring Windows backend
        "keyring.backends.Windows",
        # msal internals
        "msal.application",
        "msal.authority",
        # pycaw
        "pycaw.pycaw",
        # speech_recognition
        "speech_recognition",
        "audioop",
        # sounddevice / PortAudio (microphone input)
        "sounddevice",
        "_sounddevice_data",
    ],
    hookspath=[str(ROOT / "build" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "PyQt5",
        "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LightworksPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime*.dll", "msvcp*.dll"],
    console=False,                        # no console window (tray app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "lightworks_pro.ico"),
    manifest=str(ROOT / "build" / "lightworks_pro.manifest"),
    version=str(ROOT / "build" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime*.dll", "msvcp*.dll"],
    name="LightworksPro",
)
