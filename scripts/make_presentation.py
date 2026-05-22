"""Generate docs/Lightworks_Pro_Presentation.pptx using python-pptx."""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import os

# ── Colour palette ─────────────────────────────────────────────────────────
NAVY   = RGBColor(0x00, 0x29, 0x5C)   # dark navy (title background)
BLUE   = RGBColor(0x00, 0x55, 0xB8)   # accent blue
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
LGRAY  = RGBColor(0xF2, 0xF4, 0xF8)   # light background
DGRAY  = RGBColor(0x33, 0x33, 0x33)
GREEN  = RGBColor(0x1A, 0x7A, 0x45)
AMBER  = RGBColor(0xB8, 0x60, 0x00)

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)

prs = Presentation()
prs.slide_width  = SLIDE_W
prs.slide_height = SLIDE_H

BLANK = prs.slide_layouts[6]   # completely blank layout


# ── Helpers ────────────────────────────────────────────────────────────────

def add_rect(slide, l, t, w, h, fill=None, line=None):
    shape = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    shape.line.fill.background()
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if line:
        shape.line.color.rgb = line
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape


def txb(slide, text, l, t, w, h,
        bold=False, italic=False, size=18, color=DGRAY,
        align=PP_ALIGN.LEFT, wrap=True):
    tf = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h)).text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.bold   = bold
    run.font.italic = italic
    run.font.size   = Pt(size)
    run.font.color.rgb = color
    return tf


def bullet_box(slide, items, l, t, w, h, size=16, color=DGRAY, bullet="▸ "):
    tf = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        run = p.add_run()
        run.text = bullet + item
        run.font.size = Pt(size)
        run.font.color.rgb = color


def header_bar(slide, title, subtitle=None):
    """Navy top bar with white title."""
    add_rect(slide, 0, 0, 13.33, 1.45, fill=NAVY)
    txb(slide, title, 0.35, 0.12, 12.5, 0.75,
        bold=True, size=32, color=WHITE, align=PP_ALIGN.LEFT)
    if subtitle:
        txb(slide, subtitle, 0.35, 0.82, 12.5, 0.5,
            size=16, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.LEFT)


def footer(slide, txt="Lightworks Pro v1.2.0  ·  Abu Hoque & Lighthouse Guild, NY  ·  MIT License"):
    add_rect(slide, 0, 7.15, 13.33, 0.35, fill=NAVY)
    txb(slide, txt, 0.3, 7.17, 12.7, 0.28,
        size=10, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.LEFT)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — Title
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
add_rect(sl, 0, 0, 13.33, 7.5, fill=NAVY)
add_rect(sl, 0, 2.6, 13.33, 2.5, fill=BLUE)

txb(sl, "Lightworks Pro", 0.5, 0.6, 12.3, 1.3,
    bold=True, size=54, color=WHITE, align=PP_ALIGN.CENTER)
txb(sl, "Voice-Controlled Productivity Assistant", 0.5, 1.75, 12.3, 0.6,
    size=24, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.CENTER)
txb(sl, "for Blind & Low-Vision Professionals", 0.5, 2.3, 12.3, 0.5,
    size=20, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.CENTER)

txb(sl, "Version 1.2.0  ·  Windows 10 / 11  ·  Microsoft 365",
    0.5, 2.85, 12.3, 0.55,
    size=18, color=WHITE, align=PP_ALIGN.CENTER)
txb(sl, "Works seamlessly with JAWS · NVDA · ZoomText · Fusion",
    0.5, 3.4, 12.3, 0.5,
    size=16, color=RGBColor(0xCC, 0xDD, 0xFF), align=PP_ALIGN.CENTER)

txb(sl, "No screen required  ·  No mouse clicks  ·  No windows to navigate",
    0.5, 5.5, 12.3, 0.55,
    italic=True, size=16, color=RGBColor(0xCC, 0xDD, 0xFF), align=PP_ALIGN.CENTER)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — What is Lightworks Pro?
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "What is Lightworks Pro?",
           "A hands-free, screen-free productivity layer on top of Microsoft 365")
footer(sl)

add_rect(sl, 0.3, 1.6, 5.9, 5.3, fill=LGRAY, line=BLUE)
add_rect(sl, 6.5, 1.6, 6.5, 5.3, fill=LGRAY, line=BLUE)

txb(sl, "The Problem", 0.55, 1.7, 5.4, 0.45, bold=True, size=18, color=NAVY)
bullet_box(sl, [
    "Screen readers require visual interface navigation",
    "Meeting tools demand constant focus on windows",
    "Email and calendar still need keyboard shortcuts",
    "Teams calling requires finding and clicking contacts",
    "Switching between AT and app is disruptive",
], 0.55, 2.2, 5.5, 4.2, size=15)

txb(sl, "The Solution", 6.75, 1.7, 5.9, 0.45, bold=True, size=18, color=GREEN)
bullet_box(sl, [
    "Press one hotkey → speak a command → done",
    "Email, calendar, meetings and calls by voice",
    "Runs silently in the system tray — no window",
    "SAPI5 Text-to-Speech announces all results",
    "Zero exclusive audio streams (AT-safe)",
    "Never hooks into AT — RegisterHotKey only",
], 6.75, 2.2, 5.9, 4.2, size=15, color=GREEN)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 3 — Three Global Hotkeys
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Three Global Hotkeys — That's All You Need",
           "Press from any application at any time")
footer(sl)

for col, (hk, label, desc, clr) in enumerate([
    ("Ctrl+Shift+F1", "Listen",   "Activate the voice assistant\nand speak your command",   BLUE),
    ("Ctrl+Shift+F2", "Inbox",   "Hear your latest emails\nread aloud immediately",        GREEN),
    ("Ctrl+Shift+F3", "Meetings","Hear today's meetings\nwith join links ready",           NAVY),
    ("Ctrl+Shift+F4", "Call",    "Open Teams calling — dial by\nname, number, or group",   RGBColor(0x6A, 0x0D, 0xAD)),
]):
    x = 0.18 + col * 3.24
    add_rect(sl, x, 1.6, 3.0, 3.8, fill=clr)
    txb(sl, hk, x, 1.75, 3.0, 0.6, bold=True, size=16, color=WHITE, align=PP_ALIGN.CENTER)
    txb(sl, label, x, 2.4, 3.0, 0.55, bold=True, size=22, color=WHITE, align=PP_ALIGN.CENTER)
    txb(sl, desc, x, 3.05, 3.0, 1.5, size=14, color=WHITE, align=PP_ALIGN.CENTER)

txb(sl, "Hotkeys work system-wide — Teams, Outlook, Word, or any application.",
    0.5, 5.65, 12.3, 0.45,
    italic=True, size=15, color=BLUE, align=PP_ALIGN.CENTER)
txb(sl, "All four keys can be customised in config.json.",
    0.5, 6.1, 12.3, 0.4,
    size=14, color=DGRAY, align=PP_ALIGN.CENTER)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 4 — Automatic Features (no hotkey needed)
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Automatic Features",
           "These run in the background — no hotkey required")
footer(sl)

autos = [
    ("Meeting Alerts",
     "Announced 5 min before a meeting starts.\n"
     "Speaks: title, time, organiser, and join link status.",
     BLUE),
    ("Incoming Call Detection",
     "Polls visible Windows titles every 2 seconds.\n"
     "Announces caller name + options: accept or decline.",
     GREEN),
    ("Email Notifications",
     "Alerts on new high-priority email arrival.\n"
     "Speaks: sender and subject line.",
     NAVY),
]

for row, (title, desc, clr) in enumerate(autos):
    y = 1.65 + row * 1.75
    add_rect(sl, 0.35, y, 0.12, 1.4, fill=clr)
    txb(sl, title, 0.65, y + 0.05, 4.5, 0.45, bold=True, size=18, color=clr)
    txb(sl, desc,  0.65, y + 0.5,  12.3, 1.0, size=15, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 5 — Email & Calendar Voice Commands
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Voice Commands — Email & Calendar",
           "Press Ctrl+Shift+F1, then speak")
footer(sl)

rows = [
    ("Read my email",          "Reads the 5 most recent inbox messages"),
    ("Read email from [name]", "Filters inbox by sender name"),
    ("Compose email to [name]","Dictate a new email — subject and body by voice"),
    ("Reply to [name]",        "Reply to the latest email from that person"),
    ("Read my calendar",       "Reads all events for today"),
    ("What's tomorrow",        "Reads all events for tomorrow"),
    ("Read next week",         "Reads events for the coming 7 days"),
    ("Join next meeting",      "Opens the Teams / Zoom join link immediately"),
]

hdr_y = 1.55
add_rect(sl, 0.35, hdr_y, 5.8, 0.38, fill=NAVY)
add_rect(sl, 6.25, hdr_y, 6.7, 0.38, fill=NAVY)
txb(sl, "Say this …", 0.45, hdr_y+0.04, 5.6, 0.32, bold=True, size=14, color=WHITE)
txb(sl, "… and Lightworks Pro will …", 6.35, hdr_y+0.04, 6.5, 0.32, bold=True, size=14, color=WHITE)

for i, (cmd, result) in enumerate(rows):
    y = 2.0 + i * 0.6
    bg = LGRAY if i % 2 == 0 else WHITE
    add_rect(sl, 0.35, y, 5.8, 0.58, fill=bg)
    add_rect(sl, 6.25, y, 6.7, 0.58, fill=bg)
    txb(sl, cmd,    0.5,  y+0.08, 5.5, 0.45, bold=True, size=14, color=BLUE)
    txb(sl, result, 6.4,  y+0.08, 6.4, 0.45, size=14, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 6 — Teams Calling Voice Commands
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Voice Commands — Teams Calling",
           "Full hands-free calling via Microsoft Teams deep links")
footer(sl)

rows = [
    ("Call [name]",                   "Looks up contact → opens Teams → starts audio call"),
    ("Video call [name]",             "Same as above but launches video call"),
    ("Call [phone number]",           "Dials any PSTN number via Teams (e.g. 'call 0207 …')"),
    ("Conference call [name] and [name]", "Starts a multi-party Teams call in one command"),
    ("Answer the call",               "Accepts an incoming detected Teams call"),
    ("Decline the call",              "Rejects an incoming detected Teams call"),
]

hdr_y = 1.55
add_rect(sl, 0.35, hdr_y, 5.8, 0.38, fill=NAVY)
add_rect(sl, 6.25, hdr_y, 6.7, 0.38, fill=NAVY)
txb(sl, "Say this …", 0.45, hdr_y+0.04, 5.6, 0.32, bold=True, size=14, color=WHITE)
txb(sl, "… and Lightworks Pro will …", 6.35, hdr_y+0.04, 6.5, 0.32, bold=True, size=14, color=WHITE)

for i, (cmd, result) in enumerate(rows):
    y = 2.0 + i * 0.72
    bg = LGRAY if i % 2 == 0 else WHITE
    add_rect(sl, 0.35, y, 5.8, 0.7, fill=bg)
    add_rect(sl, 6.25, y, 6.7, 0.7, fill=bg)
    txb(sl, cmd,    0.5,  y+0.1, 5.5, 0.55, bold=True, size=14, color=BLUE)
    txb(sl, result, 6.4,  y+0.1, 6.4, 0.55, size=14, color=DGRAY)

txb(sl, "Contact search: People directory first → Outlook contacts book fallback. "
        "If contact search fails, run scripts\\grant_admin_consent.py (People.Read permission).",
    0.35, 6.55, 12.6, 0.4, italic=True, size=13, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 7 — Meeting Controls Voice Commands
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Voice Commands — Meeting Controls",
           "Works inside an active Teams meeting")
footer(sl)

rows = [
    ("Mute",          "Toggles Teams microphone mute\n+ Mute Guard: beep 880 Hz then 660 Hz (AT-safe confirmation)"),
    ("Unmute",        "Same as Mute — toggles the mute state"),
    ("Camera on/off", "Toggles Teams camera"),
    ("Raise hand",    "Raises your hand in the meeting"),
    ("Lower hand",    "Lowers your hand"),
    ("Leave meeting", "Leaves the current Teams meeting"),
    ("Who's speaking","Announces current active speaker (if available)"),
]

hdr_y = 1.55
add_rect(sl, 0.35, hdr_y, 3.5, 0.38, fill=NAVY)
add_rect(sl, 3.95, hdr_y, 9.05, 0.38, fill=NAVY)
txb(sl, "Command", 0.45, hdr_y+0.04, 3.3, 0.32, bold=True, size=14, color=WHITE)
txb(sl, "What happens", 4.05, hdr_y+0.04, 8.85, 0.32, bold=True, size=14, color=WHITE)

for i, (cmd, result) in enumerate(rows):
    y = 2.0 + i * 0.72
    bg = LGRAY if i % 2 == 0 else WHITE
    add_rect(sl, 0.35, y, 3.5,  0.7, fill=bg)
    add_rect(sl, 3.95, y, 9.05, 0.7, fill=bg)
    txb(sl, cmd,    0.5,  y+0.1, 3.2,  0.55, bold=True, size=14, color=BLUE)
    txb(sl, result, 4.1,  y+0.1, 8.7,  0.55, size=13, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 8 — To Do Voice Commands
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Voice Commands — Microsoft To Do",
           "Manage tasks hands-free via Graph API")
footer(sl)

rows = [
    ("Read my tasks",          "Reads all pending tasks — high-priority first"),
    ("Add task [description]", "Creates a new task in your default To Do list"),
    ("Complete task [name]",   "Marks the first matching task as done"),
]

hdr_y = 1.65
add_rect(sl, 0.35, hdr_y, 5.8, 0.38, fill=NAVY)
add_rect(sl, 6.25, hdr_y, 6.7, 0.38, fill=NAVY)
txb(sl, "Say this …", 0.45, hdr_y+0.04, 5.6, 0.32, bold=True, size=14, color=WHITE)
txb(sl, "… and Lightworks Pro will …", 6.35, hdr_y+0.04, 6.5, 0.32, bold=True, size=14, color=WHITE)

for i, (cmd, result) in enumerate(rows):
    y = 2.1 + i * 0.8
    bg = LGRAY if i % 2 == 0 else WHITE
    add_rect(sl, 0.35, y, 5.8, 0.78, fill=bg)
    add_rect(sl, 6.25, y, 6.7, 0.78, fill=bg)
    txb(sl, cmd,    0.5,  y+0.12, 5.5, 0.58, bold=True, size=15, color=BLUE)
    txb(sl, result, 6.4,  y+0.12, 6.4, 0.58, size=15, color=DGRAY)

txb(sl, "Navigation: after each task Lightworks Pro says 'say next or stop'.",
    0.35, 4.6, 12.6, 0.45, italic=True, size=15, color=DGRAY)
txb(sl, "Priority ordering: high-importance tasks are always spoken first.",
    0.35, 5.1, 12.6, 0.45, italic=True, size=15, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 9 — The Consent System
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "The Consent System",
           "Every action is confirmed before execution — designed for safety")
footer(sl)

steps = [
    (BLUE,  "1  Notification",
     "Lightworks Pro announces what it heard and what it plans to do.\n"
     'Example: “I heard \'call John Smith\'. Shall I call John Smith on Teams?”'),
    (AMBER, "2  Query",
     "The app waits for your spoken response.\n"
     "You have 10 seconds to reply. Silence is treated as No."),
    (GREEN, "3  Consent",
     "Say yes / confirm / do it → action proceeds.\n"
     "Say no / cancel / stop → action is cancelled silently."),
    (NAVY,  "4  Execution",
     "Action runs only after explicit verbal consent.\n"
     "Result is spoken back: success or reason for failure."),
]

for col, (clr, title, desc) in enumerate(steps):
    x = 0.3 + col * 3.2
    add_rect(sl, x, 1.65, 3.0, 5.2, fill=clr)
    txb(sl, title, x+0.1, 1.75, 2.8, 0.55, bold=True, size=17, color=WHITE, align=PP_ALIGN.CENTER)
    txb(sl, desc,  x+0.12, 2.4, 2.75, 4.2, size=14, color=WHITE)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 10 — Setup & Requirements
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Setup & System Requirements",
           "One-time configuration — then fully hands-free")
footer(sl)

add_rect(sl, 0.3, 1.6, 6.0, 5.3, fill=LGRAY, line=BLUE)
add_rect(sl, 6.6, 1.6, 6.4, 5.3, fill=LGRAY, line=GREEN)

txb(sl, "System Requirements", 0.5, 1.7, 5.6, 0.42, bold=True, size=17, color=NAVY)
bullet_box(sl, [
    "Windows 10 / 11 (64-bit)",
    "Python 3.12 or later",
    "Microsoft 365 account (Work or School)",
    "Microsoft Teams installed",
    "Working microphone + speakers / headset",
    "Internet connection",
    "AT software: JAWS, NVDA, Fusion, ZoomText (optional)",
], 0.5, 2.18, 5.7, 4.6, size=15)

txb(sl, "One-Time Setup Steps", 6.8, 1.7, 5.9, 0.42, bold=True, size=17, color=GREEN)
bullet_box(sl, [
    "1. Run LightworksPro_Setup_1.2.0.exe",
    "2. Run: pwsh -File scripts\\register_azure_app.ps1",
    "   (signs in with your Microsoft account)",
    "3. Launch Lightworks Pro — sign in via browser",
    "4. Token saved — no further sign-ins needed",
    "5. If 'call [name]' fails: run",
    "   scripts\\grant_admin_consent.py (People.Read)",
], 6.8, 2.18, 5.9, 4.6, size=15, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 11 — Assistive Technology Compatibility
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Assistive Technology Compatibility",
           "Designed from the ground up to coexist with screen readers and magnifiers")
footer(sl)

at_rows = [
    ("JAWS",     "Freedom Scientific",   "Full",  "Tested with 2024 / 2025"),
    ("NVDA",     "NV Access",            "Full",  "Tested with 2024.x"),
    ("ZoomText", "Freedom Scientific",   "Full",  "No audio conflicts"),
    ("Fusion",   "Freedom Scientific",   "Full",  "Combined SR + magnifier"),
]

hdr_y = 1.65
for col, lbl in enumerate(["Screen Reader", "Vendor", "Status", "Notes"]):
    xs = [0.4, 3.2, 6.2, 8.2]
    ws = [2.7, 2.9, 1.8, 5.0]
    add_rect(sl, xs[col], hdr_y, ws[col], 0.42, fill=NAVY)
    txb(sl, lbl, xs[col]+0.08, hdr_y+0.06, ws[col]-0.1, 0.32,
        bold=True, size=14, color=WHITE)

for i, (sr, vendor, status, notes) in enumerate(at_rows):
    y = 2.14 + i * 0.68
    bg = LGRAY if i % 2 == 0 else WHITE
    xs = [0.4, 3.2, 6.2, 8.2]
    ws = [2.7, 2.9, 1.8, 5.0]
    for col, val in enumerate([sr, vendor, status, notes]):
        add_rect(sl, xs[col], y, ws[col], 0.66, fill=bg)
        clr = GREEN if col == 2 else DGRAY
        txb(sl, val, xs[col]+0.08, y+0.12, ws[col]-0.1, 0.46,
            bold=(col == 2), size=14, color=clr)

txb(sl, "Key design decisions:", 0.4, 4.95, 12.5, 0.4, bold=True, size=15, color=NAVY)
bullet_box(sl, [
    "RegisterHotKey (Win32) — does NOT intercept events globally; AT hotkeys are unaffected",
    "SAPI5 TTS via COM STA thread — no exclusive audio stream; AT speech continues uninterrupted",
    "No pycaw exclusive mode — Mute Guard uses winsound.Beep (non-exclusive, AT-safe)",
    "No display hooks, no UI Automation server — invisible to accessibility trees",
], 0.4, 5.35, 12.7, 1.65, size=13)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 12 — Known Limitations
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
header_bar(sl, "Known Limitations — Version 1.2.0",
           "Planned for future releases unless noted otherwise")
footer(sl)

limits = [
    (AMBER, "Email & Calendar",
     "• Gmail / Google Workspace not yet connected\n"
     "• Cannot navigate to a specific thread message by voice\n"
     "• No attachment support (read or send)"),
    (AMBER, "Speech Recognition",
     "• Uses Google Cloud STT — requires internet connection\n"
     "• Offline Whisper STT blocked on Python 3.14 bindings\n"
     "• Background noise may affect recognition accuracy"),
    (AMBER, "Teams Calling",
     "• PSTN dialling requires Teams Phone System licence\n"
     "• Incoming calls shown as toast-only (no window) may\n"
     "  not be detected — enable separate call window in Teams\n"
     "• People.Read may need admin consent: run grant_admin_consent.py"),
    (AMBER, "General",
     "• Windows 10 / 11 only — no macOS or Linux\n"
     "• Microsoft 365 Work/School account required\n"
     "• Microsoft Teams desktop must be installed and running"),
]

for col, (clr, title, body) in enumerate(limits):
    x = 0.3 + (col % 2) * 6.5
    y = 1.65 + (col // 2) * 2.75
    add_rect(sl, x, y, 6.2, 2.6, fill=LGRAY, line=AMBER)
    add_rect(sl, x, y, 6.2, 0.42, fill=AMBER)
    txb(sl, title, x+0.12, y+0.06, 5.95, 0.35, bold=True, size=15, color=WHITE)
    txb(sl, body,  x+0.15, y+0.5,  5.9,  2.0,  size=13, color=DGRAY)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 13 — Closing / Thank You
# ══════════════════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(BLANK)
add_rect(sl, 0, 0, 13.33, 7.5, fill=NAVY)
add_rect(sl, 0, 2.8, 13.33, 2.2, fill=BLUE)

txb(sl, "Lightworks Pro", 0.5, 0.5, 12.3, 1.1,
    bold=True, size=48, color=WHITE, align=PP_ALIGN.CENTER)
txb(sl, "Productivity without barriers.", 0.5, 1.55, 12.3, 0.6,
    italic=True, size=26, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.CENTER)

txb(sl, "Version 1.2.0  ·  Ready to install",
    0.5, 2.9, 12.3, 0.55,
    bold=True, size=20, color=WHITE, align=PP_ALIGN.CENTER)
txb(sl, "LightworksPro_Setup_1.2.0.exe",
    0.5, 3.45, 12.3, 0.5,
    size=18, color=RGBColor(0xCC, 0xDD, 0xFF), align=PP_ALIGN.CENTER)

txb(sl, "Abu Hoque  ·  Lighthouse Guild, New York  ·  MIT License",
    0.5, 4.6, 12.3, 0.45,
    size=15, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.CENTER)
txb(sl, "Questions or feedback:",
    0.5, 5.2, 12.3, 0.45,
    size=16, color=RGBColor(0xAA, 0xCC, 0xFF), align=PP_ALIGN.CENTER)
txb(sl, "ai.apuhoque@gmail.com",
    0.5, 5.65, 12.3, 0.5,
    bold=True, size=20, color=WHITE, align=PP_ALIGN.CENTER)


# ── Save ───────────────────────────────────────────────────────────────────
os.makedirs("docs", exist_ok=True)
out = "docs/Lightworks_Pro_Presentation.pptx"
prs.save(out)
print(f"Saved: {out}")
