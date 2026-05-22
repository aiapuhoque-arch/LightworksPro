#!/usr/bin/env python3
"""
Lightworks Pro - tutorial video generator.
Run:  python build/build_tutorial_videos.py
Out:  dist/Tutorial_01_GettingStarted.mp4
      dist/Tutorial_02_Hotkeys.mp4
      dist/Tutorial_03_Meetings_Calling.mp4
      dist/Tutorial_04_Email.mp4

Each clip is a series of steps.  Every step gets its own gTTS narration,
measured audio duration, and word-cue-synchronised callout animations.
"""

import os, math, wave, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip, concatenate_videoclips
from moviepy.audio.AudioClip import CompositeAudioClip
from gtts import gTTS

# ── Resolution & palette ──────────────────────────────────────────────────────
W, H, FPS = 1920, 1080, 24
SR = 44100

NAVY  = (10,  22,  40)
NAVY2 = (18,  38,  72)
BLUE  = (30, 111, 217)
LBLUE = (80, 160, 255)
GOLD  = (245, 166,  35)
WHITE = (255, 255, 255)
BLACK = (  0,   0,   0)
GREY  = (140, 160, 185)

# ── Pre-computed gradient background ─────────────────────────────────────────
def _build_bg():
    y_g = np.linspace(0, 1, H)[:, np.newaxis]
    x_g = np.linspace(0, 1, W)[np.newaxis, :]
    g   = 0.75 * y_g + 0.25 * x_g
    arr = np.empty((H, W, 3), dtype=np.uint8)
    arr[:, :, 0] = np.clip(10 + g * 12, 0, 255)
    arr[:, :, 1] = np.clip(22 + g * 20, 0, 255)
    arr[:, :, 2] = np.clip(40 + g * 35, 0, 255)
    return arr

BG = _build_bg()

# ── Fonts ─────────────────────────────────────────────────────────────────────
FD = r"C:\Windows\Fonts"

def _f(names, size):
    for n in names:
        try:
            return ImageFont.truetype(os.path.join(FD, n), size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

F80B  = _f(["segoeuib.ttf", "arialbd.ttf"],  80)
F60B  = _f(["segoeuib.ttf", "arialbd.ttf"],  60)
F52R  = _f(["segoeui.ttf",  "arial.ttf"],    52)
F48B  = _f(["segoeuib.ttf", "arialbd.ttf"],  48)
F44R  = _f(["segoeui.ttf",  "arial.ttf"],    44)
F40L  = _f(["segoeuil.ttf", "segoeui.ttf"],  40)
F36R  = _f(["segoeui.ttf",  "arial.ttf"],    36)
F32L  = _f(["segoeuil.ttf", "segoeui.ttf"],  32)
F28R  = _f(["segoeui.ttf",  "arial.ttf"],    28)

# ── Math helpers ──────────────────────────────────────────────────────────────
def c01(v):  return max(0.0, min(1.0, float(v)))
def eio(t):  t = c01(t); return t * t * (3 - 2 * t)

# ── Render helpers ────────────────────────────────────────────────────────────
def base_frame():   return BG.copy()
def new_rgba():     return Image.new("RGBA", (W, H), (0, 0, 0, 0))
def pil2np(img):    return np.array(img.convert("RGB"))

def blend(arr, color, alpha):
    a  = c01(alpha)
    ov = np.array(color, dtype=np.float32)
    return (arr * (1 - a) + ov * a).clip(0, 255).astype(np.uint8)

def apply_fades(arr, t, dur, fi=0.5, fo=0.6):
    if t < fi:
        arr = blend(arr, BLACK, 1 - t / fi)
    if t > dur - fo:
        arr = blend(arr, BLACK, (t - (dur - fo)) / fo)
    return arr

def tbbox(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

# ── Callout pill (slide-in animated) ─────────────────────────────────────────
def callout_layer(text, y, alpha_frac, color=BLUE, font=None, direction=1):
    if font is None:
        font = F44R
    a = int(255 * c01(alpha_frac))
    tmp = Image.new("RGBA", (1, 1))
    tw, th = tbbox(ImageDraw.Draw(tmp), text, font)
    pad_x, pad_y = 40, 18
    pill_w = tw + pad_x * 2
    pill_h = th + pad_y * 2
    x = (W - pill_w) // 2 + int(180 * (1 - c01(alpha_frac)) * direction)

    layer = new_rgba()
    ld    = ImageDraw.Draw(layer)
    ld.rounded_rectangle([x, y, x + pill_w, y + pill_h],
                         radius=pill_h // 2,
                         fill=(*color[:3], int(a * 0.18)),
                         outline=(*color[:3], a), width=2)
    ld.text((x + pad_x, y + pad_y), text, font=font, fill=(*WHITE, a))
    return layer

# ── Word-cue timing ───────────────────────────────────────────────────────────
def word_cues(segments, audio_dur, lead_in=0.5):
    """
    Proportional-word-count cue times.  Short segments get minimum weight 4
    so they aren't collapsed to near-zero time.  Returns one timestamp per segment:
      cues[0]  = intro/title trigger  (~lead_in)
      cues[1+] = per-callout triggers
    """
    weights = [max(len(s.split()), 4) for s in segments]
    total   = sum(weights)
    cues, cum = [], 0
    for w in weights:
        cues.append(lead_in + (cum / total) * audio_dur)
        cum += w
    return cues

# ── Watermark ─────────────────────────────────────────────────────────────────
def draw_watermark(layer, alpha=60):
    d     = ImageDraw.Draw(layer)
    text  = "Lightworks Pro"
    tw, _ = tbbox(d, text, F28R)
    d.text((W - tw - 36, H - 48), text, font=F28R, fill=(*GOLD, alpha))

# ── Tutorial chrome ───────────────────────────────────────────────────────────

def draw_header(d, clip_title, alpha=255):
    """Top bar: brand name left, tutorial title right."""
    d.rectangle([0, 0, W, 74], fill=(*NAVY2, alpha))
    d.line([(0, 74), (W, 74)], fill=(*BLUE, alpha), width=3)

    d.text((44, 16), "LIGHTWORKS PRO", font=F36R, fill=(*WHITE, alpha))

    label = f"Tutorial: {clip_title}"
    tw, _ = tbbox(d, label, F32L)
    d.text((W - tw - 44, 20), label, font=F32L, fill=(*GOLD, alpha))


def draw_step_header(d, step_idx, total_steps, step_title, alpha=255):
    """Step indicator, step title, and gold underline."""
    indicator = f"Step {step_idx + 1} of {total_steps}"
    iw, _     = tbbox(d, indicator, F28R)
    d.text(((W - iw) // 2, 100), indicator, font=F28R, fill=(*GREY, alpha))

    tw, th = tbbox(d, step_title, F60B)
    d.text(((W - tw) // 2, 144), step_title, font=F60B, fill=(*WHITE, alpha))

    line_y = 144 + th + 14
    d.line([(W // 2 - tw // 2, line_y), (W // 2 + tw // 2, line_y)],
           fill=(*GOLD, alpha), width=3)


def draw_progress_dots(d, step_idx, total_steps, alpha=220):
    """Row of dots at foot of frame: completed=blue, current=gold, upcoming=grey."""
    dot_r  = 14
    gap    = min(120, (W - 200) // max(total_steps - 1, 1))
    total_w = gap * (total_steps - 1)
    x0     = (W - total_w) // 2
    cy     = H - 54

    for i in range(total_steps):
        cx = x0 + i * gap
        if i < step_idx:
            d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                      fill=(*BLUE, alpha))
        elif i == step_idx:
            d.ellipse([cx - dot_r - 3, cy - dot_r - 3,
                       cx + dot_r + 3, cy + dot_r + 3],
                      fill=(*GOLD, alpha))
        else:
            d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                      outline=(*GREY, alpha), width=2)


# ── Per-step frame renderer ───────────────────────────────────────────────────

def make_step_frame(t, dur, clip_title, step_idx, total_steps,
                    step_title, callouts, cues):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    ca = eio(c01(t / max(dur * 0.12, 0.4)))   # chrome fade-in 0→1

    draw_header(d, clip_title, alpha=int(255 * ca))
    draw_step_header(d, step_idx, total_steps, step_title, alpha=int(255 * ca))
    draw_progress_dots(d, step_idx, total_steps, alpha=int(220 * ca))

    # Callout pills — vertically centred in content area y 270–870
    n     = len(callouts)
    row_h = 130 if n <= 4 else 110
    y0    = (270 + 870) // 2 - (n * row_h) // 2

    for i, (text, color, dirn) in enumerate(callouts):
        delay = cues[i + 1] if (cues and i + 1 < len(cues)) else (dur * (0.30 + i * 0.15))
        if t > delay:
            p = eio(c01((t - delay) / (dur * 0.08)))
            layer.alpha_composite(callout_layer(text, y0 + i * row_h, p, color, F44R, dirn))

    draw_watermark(layer)

    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.6)


# ── Tutorial clip definitions ─────────────────────────────────────────────────
#
# CLIPS is a list of clip dicts.  Each clip has:
#   title    : str   — shown in header and used to name the output file
#   filename : str   — output MP4 filename in dist/
#   steps    : list of step dicts, each with:
#       title    : str           — step title (shown centre-frame)
#       segs     : list[str]     — narration segments; segs[0]=intro, segs[1+]=per-callout
#       callouts : list[(text, color, direction)]
#
CLIPS = [
    {
        "title":    "Getting Started",
        "filename": "Tutorial_01_GettingStarted.mp4",
        "steps": [
            {
                "title": "Installation",
                "segs": [
                    "Welcome to Lightworks Pro. "
                    "Let's get you set up. "
                    "Run the Lightworks Pro installer and follow the short setup wizard. "
                    "The application installs as a silent Windows background service. "
                    "There is no window, no screen — just a voice.",
                    "Runs silently as a Windows background service.",
                    "No window or screen required.",
                ],
                "callouts": [
                    ("Runs silently as a Windows background service", BLUE,  1),
                    ("No window or screen required",                  BLUE, -1),
                ],
            },
            {
                "title": "First Launch",
                "segs": [
                    "After installation, press Control, Shift, and F1 together to wake Lightworks Pro. "
                    "You will hear a short activation chime, followed by a welcome message. "
                    "Lightworks Pro is now listening for your first command.",
                    "Press Control Shift F1 to activate.",
                    "Listen for the activation chime.",
                    "Lightworks Pro is now listening.",
                ],
                "callouts": [
                    ("Press  Ctrl + Shift + F1  to activate", GOLD,  1),
                    ("Listen for the activation chime",       BLUE, -1),
                    ("Lightworks Pro is now listening",       BLUE,  1),
                ],
            },
            {
                "title": "Sign In",
                "segs": [
                    "Lightworks Pro needs access to your Microsoft 365 account. "
                    "It will speak a short website address and a device code. "
                    "Open that address in any browser, enter the code, and sign in with your Microsoft account. "
                    "Once complete, Lightworks Pro confirms with your voice.",
                    "Sign-in address and device code spoken aloud.",
                    "Open in any browser and enter the code.",
                    "Spoken confirmation when authorisation is complete.",
                ],
                "callouts": [
                    ("Sign-in address and code spoken aloud",       BLUE,  1),
                    ("Open in any browser — enter the device code", BLUE, -1),
                    ("Spoken confirmation when complete",           GOLD,  1),
                ],
            },
            {
                "title": "You're Ready",
                "segs": [
                    "That is it. Lightworks Pro is now running silently in the background, "
                    "connected to your calendar, your email, and Teams. "
                    "It will speak to you. You speak back. "
                    "Let's explore what it can do.",
                    "Calendar connected.",
                    "Email connected.",
                    "Teams connected.",
                ],
                "callouts": [
                    ("Calendar connected", BLUE,  1),
                    ("Email connected",    BLUE, -1),
                    ("Teams connected",    GOLD,  1),
                ],
            },
        ],
    },

    {
        "title":    "Hotkeys & Voice Commands",
        "filename": "Tutorial_02_Hotkeys.mp4",
        "steps": [
            {
                "title": "The Five Hotkeys",
                "segs": [
                    "Lightworks Pro gives you five global hotkeys that work anywhere in Windows, "
                    "including inside your screen reader. "
                    "Each hotkey triggers a specific action immediately — no voice command needed.",
                    "Control Shift F1 activates the microphone to listen for a voice command.",
                    "Control Shift F2 reads your inbox immediately.",
                    "Control Shift F3 announces your next meeting.",
                    "Control Shift F4 opens Teams calling.",
                    "Control Shift F5 quits Lightworks Pro.",
                ],
                "callouts": [
                    ("Ctrl + Shift + F1    Listen / voice command", GOLD,  1),
                    ("Ctrl + Shift + F2    Read Inbox",             BLUE, -1),
                    ("Ctrl + Shift + F3    Next Meeting",           BLUE,  1),
                    ("Ctrl + Shift + F4    Teams Call",             BLUE, -1),
                    ("Ctrl + Shift + F5    Quit",                   BLUE,  1),
                ],
            },
            {
                "title": "Speaking a Command",
                "segs": [
                    "To give a voice command: press Control Shift F1, "
                    "wait for the short activation chime, then speak clearly. "
                    "Lightworks Pro listens for up to ten seconds. "
                    "There is no wake word, no push-to-talk — just press and speak.",
                    "Step one: press Control Shift F1.",
                    "Wait for the activation chime.",
                    "Speak your command clearly.",
                ],
                "callouts": [
                    ("1.  Press  Ctrl + Shift + F1",   GOLD,  1),
                    ("2.  Wait for the chime",         BLUE, -1),
                    ("3.  Speak your command clearly", BLUE,  1),
                ],
            },
            {
                "title": "Voice-Only Commands",
                "segs": [
                    "After pressing Control Shift F1 to listen, "
                    "you can speak these additional commands.",
                    "What did I miss — a spoken briefing of missed calls, recent email, and upcoming meetings.",
                    "Teams Messages — reads your unread Teams chat messages.",
                    "Test Voice — confirms your microphone and speaker are working.",
                ],
                "callouts": [
                    ('"What did I miss"  — briefing: calls, email, meetings', BLUE,  1),
                    ('"Teams Messages"   — read unread Teams chats',          BLUE, -1),
                    ('"Test Voice"       — verify microphone and speaker',    GREY,  1),
                ],
            },
            {
                "title": "The Consent Flow",
                "segs": [
                    "For any action that changes data — sending a message, joining a meeting, "
                    "or making a call — Lightworks Pro always asks for your explicit confirmation. "
                    "Nothing ever acts silently.",
                    "The intended action is described to you aloud.",
                    "Say YES to confirm.",
                    "Say NO or CANCEL to abort.",
                    "Nothing acts without your consent.",
                ],
                "callouts": [
                    ("Action described to you aloud",       BLUE,  1),
                    ('Say  "YES"  to confirm',              GOLD, -1),
                    ('Say  "NO"  or  "CANCEL"  to abort',  BLUE,  1),
                    ("Nothing acts without your consent",   GOLD, -1),
                ],
            },
        ],
    },

    {
        "title":    "Meetings & Teams Calling",
        "filename": "Tutorial_03_Meetings_Calling.mp4",
        "steps": [
            {
                "title": "Advance Alerts",
                "segs": [
                    "Lightworks Pro monitors your calendar continuously. "
                    "You receive spoken alerts before each meeting — no setup, no action required. "
                    "Just listen.",
                    "Ten-minute spoken alert.",
                    "Five-minute spoken alert.",
                    "Alerts are announcement-only — no action needed.",
                ],
                "callouts": [
                    ("10-minute spoken alert",                BLUE,  1),
                    ("5-minute spoken alert",                 BLUE, -1),
                    ("Alerts only — no action needed",        GREY,  1),
                ],
            },
            {
                "title": "Auto-Join",
                "segs": [
                    "At your meeting's start time, Lightworks Pro begins a spoken fifteen-second countdown. "
                    "When the countdown reaches zero, it joins the meeting automatically. "
                    "Supports Teams, Zoom, Webex, and Google Meet.",
                    "Fifteen-second spoken countdown at start time.",
                    "Auto-joins Teams, Zoom, Webex, and Google Meet.",
                ],
                "callouts": [
                    ("15-second spoken countdown at start time",        GOLD,  1),
                    ("Auto-joins  Teams  |  Zoom  |  Webex  |  Meet",  BLUE, -1),
                ],
            },
            {
                "title": "Cancelling",
                "segs": [
                    "If you need to skip a meeting, "
                    "just say CANCEL at any point during the countdown. "
                    "The join is aborted immediately — no meeting is joined, no further action needed.",
                    "Say CANCEL during the countdown.",
                    "Join is aborted immediately.",
                ],
                "callouts": [
                    ('Say  "CANCEL"  during the countdown', GOLD,  1),
                    ("Join aborted — no meeting joined",    BLUE, -1),
                ],
            },
            {
                "title": "Call by Name, Extension or Number",
                "segs": [
                    "Press Control Shift F4 to open Teams calling. "
                    "Lightworks Pro asks what kind of call you want. "
                    "You can call a contact by name, dial an internal extension, "
                    "or dial an outside number.",
                    "Say call followed by a contact name for a Teams audio call.",
                    "Say extension followed by the number for an internal extension.",
                    "Say dial followed by a phone number for an outside PSTN call.",
                ],
                "callouts": [
                    ('"Call [name]"        — Teams audio call to contact', BLUE,  1),
                    ('"Extension [number]" — internal extension dial',     BLUE, -1),
                    ('"Dial [number]"      — outside PSTN phone call',     BLUE,  1),
                ],
            },
            {
                "title": "Video & Conference Calls",
                "segs": [
                    "Two more call types are available after pressing Control Shift F4. "
                    "Video call connects a one to one video call. "
                    "Conference call connects a group call with multiple participants. "
                    "Lightworks Pro guides you through each and asks for consent before connecting.",
                    "Say video call followed by a name for a one to one video call.",
                    "Say conference call followed by contact names for a group call.",
                    "Guided step by step, with consent before connecting.",
                ],
                "callouts": [
                    ('"Video call [name]"               — one-to-one video', BLUE,  1),
                    ('"Conference call [name, name...]" — group call',        BLUE, -1),
                    ("Guided step by step  |  Consent before connecting",     GOLD,  1),
                ],
            },
        ],
    },

    {
        "title":    "Email Intelligence",
        "filename": "Tutorial_04_Email.mp4",
        "steps": [
            {
                "title": "Reading Your Inbox",
                "segs": [
                    "Press Control Shift F2 to read your inbox immediately. "
                    "High-priority and flagged messages come first. "
                    "Each message is announced with sender name, subject, and a brief preview.",
                    "Press Control Shift F2 — or say read inbox after listening.",
                    "High-priority and flagged messages first.",
                    "Sender name, subject, and preview spoken.",
                ],
                "callouts": [
                    ("Ctrl + Shift + F2  — or say  \"Read Inbox\"", GOLD,  1),
                    ("High-priority and flagged messages first",     BLUE, -1),
                    ("Sender  |  Subject  |  Preview spoken",        BLUE,  1),
                ],
            },
            {
                "title": "Navigating Messages",
                "segs": [
                    "While Lightworks Pro reads your inbox, use voice commands to move through your messages.",
                    "Say NEXT for the next message.",
                    "Say REPEAT to hear the current message again.",
                    "Say FULL to hear the complete message body.",
                    "Say STOP to pause reading.",
                ],
                "callouts": [
                    ('"NEXT"    — next message',        BLUE,  1),
                    ('"REPEAT"  — hear current again',  BLUE, -1),
                    ('"FULL"    — read complete body',  BLUE,  1),
                    ('"STOP"    — pause reading',       GREY, -1),
                ],
            },
            {
                "title": "Composing",
                "segs": [
                    "To write a new email, say compose email. "
                    "To reply to the current message, say reply. "
                    "A guided wizard walks you through each field step by step.",
                    "Who are you sending to?",
                    "What is the subject?",
                    "Speak your message.",
                    "Your message is read back before sending.",
                ],
                "callouts": [
                    ('"Who are you sending to?"',         BLUE,  1),
                    ('"What is the subject?"',            BLUE, -1),
                    ('"Speak your message."',             BLUE,  1),
                    ("Message read back before sending",  GOLD, -1),
                ],
            },
            {
                "title": "Send or Save Draft",
                "segs": [
                    "After composing, Lightworks Pro reads your message back and asks what to do next. "
                    "You decide — send immediately, save as a draft, or discard. "
                    "Your choice, every time.",
                    "Say SEND to deliver immediately.",
                    "Say DRAFT to save for later.",
                    "Say CANCEL to discard.",
                ],
                "callouts": [
                    ('"SEND"    — delivers immediately', GOLD,  1),
                    ('"DRAFT"   — saved for later',      BLUE, -1),
                    ('"CANCEL"  — discards the message', BLUE,  1),
                ],
            },
        ],
    },
]


# ── Corporate background music (synthesised D major) ─────────────────────────
def generate_music(total_dur, tmp_dir, fname="bg_music.wav"):
    n   = int(total_dur * SR)
    mix = np.zeros(n, dtype=np.float64)

    CHORDS = [
        [146.83, 185.00, 220.00, 293.66],   # D major
        [196.00, 246.94, 293.66, 392.00],   # G major
        [123.47, 146.83, 185.00, 246.94],   # Bm
        [220.00, 277.18, 329.63, 440.00],   # A major
    ]
    BASS = [73.42, 98.00, 123.47, 110.00]

    BPM        = 96
    beat       = 60.0 / BPM
    bar        = beat * 4
    prog_cycle = bar * len(CHORDS)

    def adsr_env(length, atk, dec, sust, rel):
        env = np.ones(length) * sust
        a = min(atk, length)
        env[:a] = np.linspace(0, 1, a)
        d = min(dec, length - a)
        if d > 0:
            env[a:a+d] = np.linspace(1, sust, d)
        r = min(rel, length)
        env[max(0, length - r):] = np.linspace(sust, 0, r)
        return env

    for rep_start in np.arange(0, total_dur, prog_cycle):
        for ci, chord in enumerate(CHORDS):
            seg_t   = rep_start + ci * bar
            s0      = int(seg_t * SR)
            s1      = min(int((seg_t + bar) * SR), n)
            if s0 >= n: break
            seg_len = s1 - s0
            for freq in chord:
                phase = 2 * np.pi * freq * np.arange(seg_len) / SR
                sig   = (0.65 * np.sin(phase) + 0.22 * np.sin(2 * phase) +
                         0.10 * np.sin(3 * phase) + 0.03 * np.sin(4 * phase))
                env   = adsr_env(seg_len, int(0.45*SR), int(0.10*SR), 0.85, int(0.30*SR))
                mix[s0:s1] += 0.040 * sig * env

    for rep_start in np.arange(0, total_dur, prog_cycle):
        for bi, bass_f in enumerate(BASS):
            seg_t   = rep_start + bi * bar
            s0      = int(seg_t * SR)
            s1      = min(int((seg_t + bar) * SR), n)
            if s0 >= n: break
            seg_len = s1 - s0
            phase   = 2 * np.pi * bass_f * np.arange(seg_len) / SR
            sig     = (2 / np.pi) * np.arcsin(np.clip(np.sin(phase), -1, 1))
            env     = adsr_env(seg_len, int(0.05*SR), int(0.08*SR), 0.80, int(0.15*SR))
            mix[s0:s1] += 0.055 * sig * env

    MELODY = [
        (293.66, 2), (329.63, 1), (369.99, 1),
        (392.00, 2), (440.00, 2),
        (493.88, 2), (440.00, 1), (392.00, 1),
        (369.99, 4),
        (440.00, 2), (392.00, 2),
        (369.99, 2), (329.63, 2),
        (293.66, 4),
    ]
    melody_beats = sum(b for _, b in MELODY)
    melody_cycle = melody_beats * beat
    mel_start    = 8.0
    cur          = mel_start
    while cur < total_dur:
        for freq, beats in MELODY:
            note_dur = beats * beat
            s0       = int(cur * SR)
            s1       = min(int((cur + note_dur) * SR), n)
            if s0 >= n: break
            seg_len = s1 - s0
            phase   = 2 * np.pi * freq * np.arange(seg_len) / SR
            sig     = (0.60 * np.sin(phase) + 0.28 * np.sin(2 * phase) +
                       0.12 * np.sin(3 * phase))
            env     = adsr_env(seg_len, int(0.04*SR), int(0.12*SR), 0.70, int(0.12*SR))
            mix[s0:s1] += 0.022 * sig * env
            cur += note_dur
        cur = mel_start + (round((cur - mel_start) / melody_cycle) + 1) * melody_cycle

    intro_ramp = int(10 * SR)
    mix[:intro_ramp] *= np.linspace(0.30, 1.0, intro_ramp)
    mix[:int(2*SR)]  *= np.linspace(0, 1, int(2*SR))
    mix[n-int(3*SR):] *= np.linspace(1, 0, int(3*SR))

    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * 0.15

    pcm      = (mix * 32767).astype(np.int16)
    stereo   = np.column_stack([pcm, pcm])
    wav_path = os.path.join(tmp_dir, fname)
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())
    return wav_path


# ── Build one tutorial clip ───────────────────────────────────────────────────

def build_tutorial_clip(clip_def, out_path, tmp_dir):
    clip_title = clip_def["title"]
    steps      = clip_def["steps"]
    n_steps    = len(steps)
    safe_name  = clip_title[:12].replace(" ", "_")

    print(f"\n  Building: {clip_title}  ({n_steps} steps)")

    step_clips = []
    total_dur  = 0.0

    for si, step in enumerate(steps):
        step_title = step["title"]
        segs       = step["segs"]
        callouts   = step["callouts"]

        full_text = " ".join(segs)
        mp3       = os.path.join(tmp_dir, f"tut_{safe_name}_{si:02d}.mp3")
        gTTS(full_text, lang="en", tld="com", slow=False).save(mp3)
        ad = AudioFileClip(mp3).duration
        vd = ad + 1.0

        cues = word_cues(segs, ad, lead_in=0.5)
        total_dur += vd
        print(f"    Step {si+1}/{n_steps} '{step_title}'  "
              f"audio={ad:.2f}s  video={vd:.2f}s  "
              f"cues={[f'{c:.1f}' for c in cues]}")

        clip = VideoClip(
            lambda t, si=si, vd=vd, cues=cues,
                      title=step_title, callouts=callouts:
                make_step_frame(t, vd, clip_title, si, n_steps, title, callouts, cues),
            duration=vd,
        )
        audio = AudioFileClip(mp3).with_start(0.5)
        clip  = clip.with_audio(audio)
        step_clips.append(clip)

    full_clip = concatenate_videoclips(step_clips, method="compose")

    print(f"    Synthesising music ({total_dur:.1f}s)...")
    music_path = generate_music(total_dur + 2.0, tmp_dir,
                                fname=f"music_{safe_name}.wav")
    music = AudioFileClip(music_path)
    if music.duration > full_clip.duration:
        try:
            music = music.subclipped(0, full_clip.duration)
        except AttributeError:
            music = music.subclip(0, full_clip.duration)

    mixed     = CompositeAudioClip([full_clip.audio, music])
    full_clip = full_clip.with_audio(mixed)

    frame_count = int(full_clip.duration * FPS)
    print(f"    Rendering {out_path}")
    print(f"    ({frame_count} frames, {total_dur:.1f}s — please wait...)")
    full_clip.write_videofile(
        out_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        logger="bar",
    )
    sz = os.path.getsize(out_path) / 1_048_576
    print(f"    Done: {sz:.1f} MB")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "dist")
    os.makedirs(out_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp()
    print(f"Temp dir: {tmp_dir}")
    print(f"Output:   {out_dir}")
    print(f"Building {len(CLIPS)} tutorial clips...\n")

    for clip_def in CLIPS:
        out_path = os.path.join(out_dir, clip_def["filename"])
        build_tutorial_clip(clip_def, out_path, tmp_dir)

    print("\nAll tutorial clips complete.")
    for clip_def in CLIPS:
        p = os.path.join(out_dir, clip_def["filename"])
        if os.path.exists(p):
            sz = os.path.getsize(p) / 1_048_576
            print(f"  {clip_def['filename']}  {sz:.1f} MB")


if __name__ == "__main__":
    main()
