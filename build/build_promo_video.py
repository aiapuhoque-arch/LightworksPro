#!/usr/bin/env python3
"""
Lightworks Pro - promotional video generator.
Run:  python build/build_promo_video.py
Out:  dist/LightworksPro_Promo.mp4

Sync:  Per-scene narration MP3 -> measure real audio duration -> set video
       clip duration to match. Every callout/reveal scales to the actual
       scene duration so visuals stay locked to the words.
Music: Synthesised corporate D-major bed, mixed at -14 dB under narration.
Brand: "Lightworks Pro" + "Lighthouse Guild" both highlighted in gold.
"""

import os, math, wave, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioFileClip, concatenate_videoclips
from moviepy.audio.AudioClip import CompositeAudioClip
from gtts import gTTS

# ── Resolution & palette ──────────────────────────────────────────────────────
W, H, FPS = 1920, 1080, 24
SR = 44100   # music sample rate

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

F100B = _f(["segoeuib.ttf","arialbd.ttf"], 100)
F80B  = _f(["segoeuib.ttf","arialbd.ttf"],  80)
F72B  = _f(["segoeuib.ttf","arialbd.ttf"],  72)
F60B  = _f(["segoeuib.ttf","arialbd.ttf"],  60)
F52R  = _f(["segoeui.ttf", "arial.ttf"],    52)
F50L  = _f(["segoeuil.ttf","segoeui.ttf"],  50)
F48B  = _f(["segoeuib.ttf","arialbd.ttf"],  48)
F44R  = _f(["segoeui.ttf", "arial.ttf"],    44)
F40L  = _f(["segoeuil.ttf","segoeui.ttf"],  40)
F36R  = _f(["segoeui.ttf", "arial.ttf"],    36)
F32L  = _f(["segoeuil.ttf","segoeui.ttf"],  32)
F28R  = _f(["segoeui.ttf", "arial.ttf"],    28)

# ── Math ──────────────────────────────────────────────────────────────────────
def c01(v):  return max(0.0, min(1.0, float(v)))
def eio(t):  t = c01(t); return t * t * (3 - 2 * t)
def eo(t):   t = c01(t); return 1 - (1 - t) ** 2

# ── Render helpers ────────────────────────────────────────────────────────────
def base_frame():   return BG.copy()
def new_rgba():     return Image.new("RGBA", (W, H), (0, 0, 0, 0))
def pil2np(img):    return np.array(img.convert("RGB"))

def blend(arr, color, alpha):
    a  = c01(alpha)
    ov = np.array(color, dtype=np.float32)
    return (arr * (1 - a) + ov * a).clip(0, 255).astype(np.uint8)

def apply_fades(arr, t, dur, fi=0.6, fo=0.6):
    if t < fi:
        arr = blend(arr, BLACK, 1 - t / fi)
    if t > dur - fo:
        arr = blend(arr, BLACK, (t - (dur - fo)) / fo)
    return arr

def tbbox(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

# ── Icons ─────────────────────────────────────────────────────────────────────
def icon_calendar(draw, icx, icy, size=64, color=WHITE, alpha=255):
    c  = (*color[:3], alpha)
    x1, y1 = icx - size // 2, icy - size // 2
    x2, y2 = icx + size // 2, icy + size // 2
    top = y1 + size // 5
    draw.rounded_rectangle([x1, y1, x2, y2], radius=6, outline=c, width=3)
    draw.line([(x1, top), (x2, top)], fill=c, width=2)
    for i in range(1, 4):
        gx = x1 + i * size // 4
        draw.line([(gx, top), (gx, y2)], fill=c, width=1)
    for j in range(1, 3):
        gy = top + j * (y2 - top) // 3
        draw.line([(x1, gy), (x2, gy)], fill=c, width=1)

def icon_envelope(draw, icx, icy, size=64, color=WHITE, alpha=255):
    c  = (*color[:3], alpha)
    x1, y1 = icx - size // 2, icy - size // 3
    x2, y2 = icx + size // 2, icy + size // 3
    draw.rounded_rectangle([x1, y1, x2, y2], radius=6, outline=c, width=3)
    draw.line([(x1, y1), (icx, icy)], fill=c, width=2)
    draw.line([(x2, y1), (icx, icy)], fill=c, width=2)

def icon_lock(draw, icx, icy, size=80, color=WHITE, alpha=255):
    c  = (*color[:3], alpha)
    bx1, by1 = icx - size // 3, icy - size // 10
    bx2, by2 = icx + size // 3, icy + size // 2
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=8, outline=c, width=3)
    r = size // 4
    draw.arc([icx - r, icy - size // 2, icx + r, icy + size // 10],
             start=180, end=0, fill=c, width=3)
    draw.ellipse([icx - 7, icy + size // 10, icx + 7, icy + size // 10 + 14],
                 outline=c, width=2)

# ── Callout pill ──────────────────────────────────────────────────────────────
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

# ── Callout timing helper ─────────────────────────────────────────────────────
def cue_times(n, dur, title_end=2.0, hold=1.0, fi=0.6, fo=0.6):
    """Space n cue points evenly through the usable window of a scene."""
    win_s = max(title_end + 0.3, fi + 0.3)
    win_e = dur - fo - hold
    if win_e <= win_s:
        win_e = dur - fo
    if n == 1:
        return [win_s]
    step = (win_e - win_s) / (n - 1)
    return [win_s + i * step for i in range(n)]

def word_cues(segments, audio_dur, lead_in=0.5):
    """
    Estimate the absolute start time of each narration segment by proportional
    word count.  Short segments (like "Notify.") get a minimum weight of 4
    words so they aren't collapsed to near-zero time.
    Returns one cue time per segment:
      cues[0]  = title/intro trigger (~lead_in)
      cues[1+] = callout trigger times
    """
    weights = [max(len(s.split()), 4) for s in segments]
    total   = sum(weights)
    cues, cum = [], 0
    for w in weights:
        cues.append(lead_in + (cum / total) * audio_dur)
        cum += w
    return cues

# ── "Lightworks Pro" watermark (bottom-right, feature scenes) ────────────────
def draw_watermark(layer, alpha=60):
    d     = ImageDraw.Draw(layer)
    text  = "Lightworks Pro"
    font  = F28R
    tw, _ = tbbox(d, text, font)
    x = W - tw - 36
    y = H - 48
    d.text((x, y), text, font=font, fill=(*GOLD, alpha))

# ── Scene 1: The Problem (12 s nominal) ───────────────────────────────────────
def s1(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    cursor_end = min(dur * 0.30, 4.0)
    if t < cursor_end:
        if int(t * 2) % 2 == 0:
            d.rectangle([W // 2 - 3, H // 2 - 58, W // 2 + 3, H // 2 + 58],
                        fill=(*BLUE, 255))

    text_start = min(dur * 0.25, 3.0)
    if t > text_start:
        p     = eio(c01((t - text_start) / (dur * 0.30)))
        a     = int(255 * p)
        slide = int(28 * (1 - p))
        yb    = H // 2 - 105
        lines = [
            ("Every day, millions of professionals", F52R, WHITE),
            ("navigate a digital world",             F52R, WHITE),
            ("built for sight.",                     F72B, GOLD),
        ]
        for i, (txt, fnt, col) in enumerate(lines):
            tw, _ = tbbox(d, txt, fnt)
            d.text(((W - tw) // 2, yb + i * 76 + slide), txt, font=fnt, fill=(*col, a))

    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.8, fo=0.8)


# ── Scene 2: The Reveal (10 s nominal) ────────────────────────────────────────
def s2(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    wave_end   = dur * 0.50
    logo_start = dur * 0.28
    tag_start  = dur * 0.64

    if t < wave_end:
        amp     = int(110 * eio(c01(t / (dur * 0.15))))
        w_alpha = int(255 * (1 - eio(c01((t - logo_start) / (dur * 0.22))))) \
                  if t > logo_start else 255
        pts1, pts2 = [], []
        n = 200
        for i in range(n):
            frac = i / (n - 1)
            px   = (W - 900) // 2 + int(frac * 900)
            env  = math.exp(-((frac - 0.5) ** 2) * 8)
            y1   = H // 2 + amp * math.sin(frac * math.pi * 8 + t * 4.2) * env
            y2   = H // 2 + (amp // 2) * math.sin(frac * math.pi * 5 + t * 3.0 + 1) * env
            pts1.append((px, int(y1)))
            pts2.append((px, int(y2)))
        if len(pts1) > 1:
            d.line(pts1, fill=(*BLUE,  w_alpha), width=4)
            d.line(pts2, fill=(*LBLUE, w_alpha // 2), width=2)

    if t > logo_start:
        p  = eio(c01((t - logo_start) / (dur * 0.25)))
        a  = int(255 * p)
        sl = int(32 * (1 - p))
        yL = H // 2 - 110

        # "LIGHTWORKS" in white
        lw_tw, _ = tbbox(d, "LIGHTWORKS", F100B)
        d.text(((W - lw_tw) // 2, yL + sl), "LIGHTWORKS", font=F100B, fill=(*WHITE, a))

        # "PRO" in gold — the brand name in gold
        pro_tw, _ = tbbox(d, "PRO", F50L)
        d.text(((W - pro_tw) // 2, yL + 108 + sl), "PRO", font=F50L, fill=(*GOLD, a))

        line_w = max(lw_tw, pro_tw)
        d.line([(W // 2 - line_w // 2, yL + 168 + sl),
                (W // 2 + line_w // 2, yL + 168 + sl)],
               fill=(*BLUE, a), width=4)

        if t > tag_start:
            tp = eio(c01((t - tag_start) / (dur * 0.22)))
            ta = int(255 * tp)

            tag    = "Your voice.  Your workspace.  Your pace."
            ttw, _ = tbbox(d, tag, F40L)
            d.text(((W - ttw) // 2, yL + 214), tag, font=F40L, fill=(*GREY, ta))

    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.8)


# ── Scene 3: Architecture (13 s nominal) ─────────────────────────────────────
def s3(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    hub_p = eio(c01(t / (dur * 0.18)))
    ha    = int(255 * hub_p)
    hx, hy = W // 2, H // 2 - 80
    hw, hh = 370, 90

    d.rounded_rectangle([hx - hw // 2, hy - hh // 2, hx + hw // 2, hy + hh // 2],
                        radius=22, fill=(*BLUE, int(ha * 0.85)),
                        outline=(*LBLUE, ha), width=2)
    hub_tw, _ = tbbox(d, "Lightworks Pro", F48B)
    d.text(((W - hub_tw) // 2, hy - 22), "Lightworks Pro", font=F48B, fill=(*WHITE, ha))

    satellites = [
        ("Email",              W // 2 - 540, hy + 185),
        ("Calendar",           W // 2 - 170, hy + 265),
        ("Teams / Zoom",       W // 2 + 170, hy + 265),
        ("Teams Calls / Phone",W // 2 + 540, hy + 185),
    ]
    delays = cues[1:5] if (cues and len(cues) >= 5) else cue_times(4, dur, title_end=dur * 0.15, hold=1.0)
    for i, (label, sx, sy) in enumerate(satellites):
        if t > delays[i]:
            p = eio(c01((t - delays[i]) / (dur * 0.09)))
            a = int(255 * p)
            d.line([(hx, hy + hh // 2), (sx, sy - 32)], fill=(*BLUE, a // 2), width=2)
            d.ellipse([sx - 68, sy - 30, sx + 68, sy + 30],
                      outline=(*BLUE, a), fill=(*NAVY2, a), width=2)
            ltw, _ = tbbox(d, label, F32L)
            d.text((sx - ltw // 2, sy - 14), label, font=F32L, fill=(*WHITE, a))

    at_start = dur * 0.75
    if t > at_start:
        bp  = eio(c01((t - at_start) / (dur * 0.12)))
        ba  = int(255 * bp)
        bar = "JAWS  |  NVDA  |  Fusion  |  ZoomText"
        btw, _ = tbbox(d, bar, F44R)
        d.text(((W - btw) // 2, hy + 360), bar, font=F44R, fill=(*GREY, ba))
        sub = "Coexists with your screen reader - never conflicts"
        stw, _ = tbbox(d, sub, F32L)
        d.text(((W - stw) // 2, hy + 415), sub, font=F32L, fill=(*GREY, ba // 2))

    draw_watermark(layer)
    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.7)


# ── Scene 4: Meetings (15 s nominal) ─────────────────────────────────────────
MEET_ROWS = [
    ("10 & 5 minute advance alerts  (announce only)", BLUE,  1),
    ("Auto-joins at start time - 15-second countdown", BLUE, -1),
    ('"CANCEL" aborts the countdown at any time',      GOLD,  1),
    ("Teams  |  Zoom  |  Webex  |  Google Meet",       BLUE, -1),
]

def s4(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    tp = eio(c01(t / (dur * 0.12)))
    ta = int(255 * tp)
    icon_calendar(d, W // 2, 110, size=64, color=WHITE, alpha=ta)
    title_tw, _ = tbbox(d, "Meetings", F80B)
    d.text(((W - title_tw) // 2, 172), "Meetings", font=F80B, fill=(*WHITE, ta))

    delays = cues[1:5] if (cues and len(cues) >= 5) else cue_times(4, dur, title_end=min(2.0, dur * 0.14), hold=0.8)
    y0, row_h = 345, 140
    for i, (text, color, dirn) in enumerate(MEET_ROWS):
        if t > delays[i]:
            p = eio(c01((t - delays[i]) / (dur * 0.08)))
            layer.alpha_composite(callout_layer(text, y0 + i * row_h, p, color, F44R, dirn))

    draw_watermark(layer)
    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.7)


# ── Scene 5: Teams Calling (15 s nominal) ────────────────────────────────────
TEAMS_ROWS = [
    ("Dial any contact by name or phone number", BLUE,  1),
    ("Video call  |  Conference call",           BLUE, -1),
]

def icon_phone(draw, icx, icy, size=64, color=WHITE, alpha=255):
    """Simple telephone handset icon."""
    c  = (*color[:3], alpha)
    s  = size
    # Handset arc
    draw.arc([icx - s // 2, icy - s // 3, icx + s // 2, icy + s // 3],
             start=200, end=340, fill=c, width=int(s * 0.14))
    # Earpiece cap
    draw.ellipse([icx - s // 2 - 4, icy - 6, icx - s // 2 + 10, icy + 6],
                 fill=c)
    # Mouthpiece cap
    draw.ellipse([icx + s // 2 - 10, icy - 6, icx + s // 2 + 4, icy + 6],
                 fill=c)

def s5_teams(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    tp = eio(c01(t / (dur * 0.12)))
    ta = int(255 * tp)
    icon_phone(d, W // 2, 110, size=64, color=WHITE, alpha=ta)
    title_tw, _ = tbbox(d, "Teams Calling", F80B)
    d.text(((W - title_tw) // 2, 172), "Teams Calling", font=F80B, fill=(*WHITE, ta))

    delays = cues[1:3] if (cues and len(cues) >= 3) else cue_times(2, dur, title_end=min(2.0, dur * 0.14), hold=0.8)
    y0, row_h = 415, 160
    for i, (text, color, dirn) in enumerate(TEAMS_ROWS):
        if t > delays[i]:
            p = eio(c01((t - delays[i]) / (dur * 0.08)))
            layer.alpha_composite(callout_layer(text, y0 + i * row_h, p, color, F44R, dirn))

    draw_watermark(layer)
    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.7)


# ── Scene 6: Email Intelligence (15 s nominal) ────────────────────────────────
EMAIL_ROWS = [
    ("High-priority messages read first",    BLUE,  1),
    ('Navigate by voice - say  "NEXT"',      BLUE, -1),
    ("Guided compose wizard - step by step", BLUE,  1),
    ("Send immediately  or  Save as Draft",  GOLD, -1),
]

def s6_email(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    tp = eio(c01(t / (dur * 0.12)))
    ta = int(255 * tp)
    icon_envelope(d, W // 2, 110, size=64, color=WHITE, alpha=ta)
    title_tw, _ = tbbox(d, "Email Intelligence", F72B)
    d.text(((W - title_tw) // 2, 172), "Email Intelligence", font=F72B, fill=(*WHITE, ta))

    delays = cues[1:5] if (cues and len(cues) >= 5) else cue_times(4, dur, title_end=min(2.0, dur * 0.14), hold=0.8)
    y0, row_h = 345, 140
    for i, (text, color, dirn) in enumerate(EMAIL_ROWS):
        if t > delays[i]:
            p = eio(c01((t - delays[i]) / (dur * 0.08)))
            layer.alpha_composite(callout_layer(text, y0 + i * row_h, p, color, F44R, dirn))

    draw_watermark(layer)
    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.7)


# ── Scene 7: Security & Trust (10 s nominal) ─────────────────────────────────
STEPS = [("NOTIFY", BLUE), ("QUERY", BLUE), ("CONSENT", BLUE), ("EXECUTE", GOLD)]

def s7_security(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    lp = eio(c01(t / (dur * 0.15)))
    icon_lock(d, W // 2, H // 2 - 220, size=90, color=WHITE, alpha=int(255 * lp))

    step_gap = 370
    total_w  = step_gap * (len(STEPS) - 1)
    x0, sy   = W // 2 - total_w // 2, H // 2 - 30

    delays = cues[1:5] if (cues and len(cues) >= 5) else cue_times(4, dur, title_end=min(1.5, dur * 0.14), hold=1.5)
    for i, (label, color) in enumerate(STEPS):
        if t > delays[i]:
            p  = eio(c01((t - delays[i]) / (dur * 0.08)))
            a  = int(255 * p)
            sx = x0 + i * step_gap

            d.ellipse([sx - 58, sy - 38, sx + 58, sy + 38],
                      fill=(*color, int(a * 0.25)),
                      outline=(*color, a), width=3)
            ltw, _ = tbbox(d, label, F36R)
            d.text((sx - ltw // 2, sy - 18), label, font=F36R, fill=(*WHITE, a))

            if i < len(STEPS) - 1 and t > delays[i] + 0.3:
                ap  = eio(c01((t - delays[i] - 0.3) / (dur * 0.06)))
                aa  = int(255 * ap)
                ax1 = sx + 62;  ax2 = sx + step_gap - 62
                d.line([(ax1, sy), (ax2, sy)], fill=(*GREY, aa), width=2)
                d.polygon([(ax2, sy - 9), (ax2 + 16, sy), (ax2, sy + 9)], fill=(*GREY, aa))

    sub_start = dur * 0.78
    if t > sub_start:
        sp  = eio(c01((t - sub_start) / (dur * 0.12)))
        sa  = int(255 * sp)
        sub = "Nothing acts without your explicit voice confirmation."
        stw, _ = tbbox(d, sub, F44R)
        d.text(((W - stw) // 2, sy + 105), sub, font=F44R, fill=(*WHITE, sa))

    draw_watermark(layer)
    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=0.8)


# ── Scene 8: Call to Action (15 s nominal) ────────────────────────────────────
def s8_cta(t, dur, cues=None):
    arr   = base_frame()
    layer = new_rgba()
    d     = ImageDraw.Draw(layer)

    # Pulse ring
    if t > 0.3:
        phase = (t - 0.3) % 3.0
        pr    = int(200 + phase / 3.0 * 200)
        pa    = int(255 * (1 - phase / 3.0) * 0.35)
        d.ellipse([W // 2 - pr, H // 2 - 270 - pr,
                   W // 2 + pr, H // 2 - 270 + pr],
                  outline=(*BLUE, pa), width=3)

    # ── LIGHTWORKS PRO logo ──
    lp = eio(c01(t / (dur * 0.18)))
    la = int(255 * lp)
    sl = int(30 * (1 - lp))
    yL = H // 2 - 335

    lw_tw, _ = tbbox(d, "LIGHTWORKS", F100B)
    d.text(((W - lw_tw) // 2, yL + sl), "LIGHTWORKS", font=F100B, fill=(*WHITE, la))

    pro_tw, _ = tbbox(d, "PRO", F60B)
    d.text(((W - pro_tw) // 2, yL + 108 + sl), "PRO", font=F60B, fill=(*GOLD, la))

    line_w = max(lw_tw, pro_tw)
    d.line([(W // 2 - line_w // 2, yL + 178 + sl),
            (W // 2 + line_w // 2, yL + 178 + sl)],
           fill=(*BLUE, la), width=5)

    # Tagline (18% in)
    if t > dur * 0.18:
        tp  = eio(c01((t - dur * 0.18) / (dur * 0.16)))
        ta  = int(255 * tp)
        tag = "Your voice.  Your workspace.  Your pace."
        ttw, _ = tbbox(d, tag, F52R)
        d.text(((W - ttw) // 2, yL + 218), tag, font=F52R, fill=(*WHITE, ta))

    # Info lines (33%, 48%, 62%)
    info_lines = [
        ("Available now for Windows  |  Microsoft 365",            F40L, WHITE),
        ("Works alongside  JAWS  |  NVDA  |  Fusion  |  ZoomText", F36R, GREY),
    ]
    for i, (line, fnt, col) in enumerate(info_lines):
        delay = dur * (0.33 + i * 0.15)
        if t > delay:
            p  = eio(c01((t - delay) / (dur * 0.12)))
            a  = int(255 * p)
            ltw, _ = tbbox(d, line, fnt)
            d.text(((W - ltw) // 2, yL + 316 + i * 66), line, font=fnt, fill=(*col, a))


    bg = Image.fromarray(arr).convert("RGBA")
    bg.alpha_composite(layer)
    return apply_fades(pil2np(bg), t, dur, fi=0.5, fo=1.5)


# ── Corporate background music (synthesised D major) ─────────────────────────
def generate_music(total_dur, tmp_dir):
    """
    Synthesise a warm D-major corporate pad track.
    D major progression: D - G - Bm - A (4 bars each = 16 s, repeating)
    Instruments: chord pads (sine + harmonics), bass, simple melody.
    Final volume scaled to ~15% amplitude so narration stays clearly audible.
    """
    n   = int(total_dur * SR)
    mix = np.zeros(n, dtype=np.float64)
    t   = np.arange(n, dtype=np.float64) / SR

    # -- frequencies (Hz) --
    # D2=73.42  G2=98.00  B2=123.47  A2=110.00
    # D3=146.83 F#3=185.00 G3=196.00 B3=246.94 A3=220.00 C#4=277.18 E4=329.63
    # D4=293.66 F#4=369.99 G4=392.00 A4=440.00 D5=587.33

    CHORDS = [
        [146.83, 185.00, 220.00, 293.66],   # D major
        [196.00, 246.94, 293.66, 392.00],   # G major
        [123.47, 146.83, 185.00, 246.94],   # Bm
        [220.00, 277.18, 329.63, 440.00],   # A major
    ]
    BASS = [73.42, 98.00, 123.47, 110.00]  # root notes D G B A

    BPM        = 96
    beat       = 60.0 / BPM           # ~0.625 s
    bar        = beat * 4             # ~2.5 s
    prog_cycle = bar * len(CHORDS)    # ~10 s

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

    # -- chord pads --
    for rep_start in np.arange(0, total_dur, prog_cycle):
        for ci, chord in enumerate(CHORDS):
            seg_t  = rep_start + ci * bar
            s0     = int(seg_t * SR)
            s1     = min(int((seg_t + bar) * SR), n)
            if s0 >= n:
                break
            seg_len = s1 - s0
            for freq in chord:
                phase = 2 * np.pi * freq * np.arange(seg_len) / SR
                sig   = (0.65 * np.sin(phase) +
                         0.22 * np.sin(2 * phase) +
                         0.10 * np.sin(3 * phase) +
                         0.03 * np.sin(4 * phase))
                env   = adsr_env(seg_len,
                                 int(0.45 * SR), int(0.10 * SR),
                                 0.85, int(0.30 * SR))
                mix[s0:s1] += 0.040 * sig * env

    # -- bass line (one note per bar, triangle wave) --
    for rep_start in np.arange(0, total_dur, prog_cycle):
        for bi, bass_f in enumerate(BASS):
            seg_t  = rep_start + bi * bar
            s0     = int(seg_t * SR)
            s1     = min(int((seg_t + bar) * SR), n)
            if s0 >= n:
                break
            seg_len = s1 - s0
            phase   = 2 * np.pi * bass_f * np.arange(seg_len) / SR
            sig     = (2 / np.pi) * np.arcsin(np.clip(np.sin(phase), -1, 1))
            env     = adsr_env(seg_len,
                               int(0.05 * SR), int(0.08 * SR),
                               0.80, int(0.15 * SR))
            mix[s0:s1] += 0.055 * sig * env

    # -- simple melody (enters at 8 s) --
    # D major scale ascending/arch pattern
    MELODY = [  # (freq_Hz, beats)
        (293.66, 2), (329.63, 1), (369.99, 1),
        (392.00, 2), (440.00, 2),
        (493.88, 2), (440.00, 1), (392.00, 1),
        (369.99, 4),
        (440.00, 2), (392.00, 2),
        (369.99, 2), (329.63, 2),
        (293.66, 4),
    ]
    melody_total_beats = sum(b for _, b in MELODY)
    melody_cycle = melody_total_beats * beat

    mel_start = 8.0
    cur = mel_start
    while cur < total_dur:
        for freq, beats in MELODY:
            note_dur = beats * beat
            s0       = int(cur * SR)
            s1       = min(int((cur + note_dur) * SR), n)
            if s0 >= n:
                break
            seg_len = s1 - s0
            phase   = 2 * np.pi * freq * np.arange(seg_len) / SR
            sig     = (0.60 * np.sin(phase) +
                       0.28 * np.sin(2 * phase) +
                       0.12 * np.sin(3 * phase))
            env     = adsr_env(seg_len,
                               int(0.04 * SR), int(0.12 * SR),
                               0.70, int(0.12 * SR))
            mix[s0:s1] += 0.022 * sig * env
            cur += note_dur
        cur = mel_start + (round((cur - mel_start) / melody_cycle) + 1) * melody_cycle

    # -- global dynamics --
    # Intro: quiet (builds over first 10 s)
    intro_ramp = int(10 * SR)
    mix[:intro_ramp] *= np.linspace(0.30, 1.0, intro_ramp)

    # Fade in (first 2 s)
    fi = int(2 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)

    # Fade out (last 3 s)
    fo = int(3 * SR)
    mix[n - fo:] *= np.linspace(1, 0, fo)

    # Normalise then scale to 15% amplitude so narration dominates
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * 0.15

    # Save as stereo 16-bit WAV
    pcm     = (mix * 32767).astype(np.int16)
    stereo  = np.column_stack([pcm, pcm])
    wav_path = os.path.join(tmp_dir, "bg_music.wav")
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())

    return wav_path


# ── Per-scene narration segments ──────────────────────────────────────────────
# Each entry is a list of text segments.  Segment 0 = intro/title;
# segments 1..n = one per callout/satellite/step, in visual order.
# word_cues() converts these into precise trigger times.
SCENE_SEGS = [
    # 1 – The Problem (single block, no callouts)
    ["Every day, millions of professionals rely on digital tools. "
     "To stay connected, to lead meetings, to send emails. "
     "And every tool assumes they can see a screen."],

    # 2 – The Reveal (single block)
    ["Lightworks Pro changes that. "
     "A voice-first productivity assistant, "
     "built from the ground up for blind and visually impaired professionals. "
     "Working silently alongside your screen reader, never against it."],

    # 3 – Architecture  (intro + 4 satellite labels)
    ["Running silently as a background service, Lightworks Pro connects to Microsoft 365.",
     "Your email.",
     "Your calendar.",
     "Teams and Zoom.",
     "Teams Calls and Phone. Delivering everything through your natural voice."],

    # 4 – Meetings  (intro + 4 callouts)
    ["Meetings. Handled. Lightworks Pro watches your calendar around the clock.",
     "Announces your next meeting at ten minutes and five minutes. No action required.",
     "At start time, it counts down and joins automatically.",
     "Say cancel if plans change.",
     "Teams, Zoom, Webex, and Google Meet. All supported."],

    # 5 – Teams Calling  (intro + 2 callouts)
    ["Teams Calling puts full phone capabilities at your voice.",
     "Dial any contact by name, or by phone number.",
     "Video call, or conference call with multiple participants."],

    # 6 – Email Intelligence  (intro + 4 callouts)
    ["Email Intelligence reads your inbox to you.",
     "High-priority messages first.",
     "Navigate with your voice. Say next.",
     "A guided compose wizard walks you through each step.",
     "Send immediately, or save as a draft. Your choice, every time."],

    # 7 – Security  (intro + 4 steps)
    ["Privacy and safety are built into every action.",
     "Notify.",
     "Query.",
     "Consent.",
     "Execute. Lightworks Pro never acts without your explicit voice confirmation. "
     "No silent automation. No surprises."],

    # 8 – Call to Action (single block)
    ["Lightworks Pro. Available now for Windows, with Microsoft 365. "
     "Built for professionals who rely on JAWS, NVDA, Fusion, and ZoomText. "
     "Engineered to stay out of their way. "
     "Your voice. Your workspace. Your pace."],
]

SCENE_FNS   = [s1, s2, s3, s4, s5_teams, s6_email, s7_security, s8_cta]
SCENE_NAMES = [
    "The Problem", "The Reveal", "Architecture",
    "Meetings", "Teams Calling", "Email Intelligence",
    "Security & Trust", "Call to Action",
]


# ── Assembly ──────────────────────────────────────────────────────────────────
def main():
    root     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir  = os.path.join(root, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "LightworksPro_Promo.mp4")

    tmp_dir = tempfile.mkdtemp()
    print(f"Temp dir: {tmp_dir}\n")

    n_scenes = len(SCENE_NAMES)

    # 1 ── Generate per-scene narration; measure real audio duration
    print("Generating per-scene narration...")
    audio_paths, audio_durs = [], []
    for i, (name, segs) in enumerate(zip(SCENE_NAMES, SCENE_SEGS)):
        full_text = " ".join(segs)
        mp3       = os.path.join(tmp_dir, f"narr_{i:02d}.mp3")
        print(f"  [{i+1}/{n_scenes}] {name}")
        gTTS(full_text, lang="en", tld="com", slow=False).save(mp3)
        dur = AudioFileClip(mp3).duration
        audio_paths.append(mp3)
        audio_durs.append(dur)
        print(f"         {dur:.2f}s")

    # 2 ── Build video clips with word-cue sync
    #       duration = audio_dur + 1 s  (0.5 s lead-in before speech + 0.5 s tail)
    #       cues = word_cues(segments, audio_dur) shifted by 0.5 s lead-in
    print("\nBuilding video clips (word-cue sync)...")
    scene_clips = []
    total_dur   = 0.0
    for i, (fn, name, ad, segs) in enumerate(zip(SCENE_FNS, SCENE_NAMES, audio_durs, SCENE_SEGS)):
        vd   = ad + 1.0
        cues = word_cues(segs, ad, lead_in=0.5)   # 0.5 s lead-in matches audio.with_start(0.5)
        total_dur += vd
        print(f"  [{i+1}/{n_scenes}] {name}  audio={ad:.2f}s  video={vd:.2f}s  cues={[f'{c:.1f}' for c in cues]}")
        _fn, _vd, _cues = fn, vd, cues
        clip  = VideoClip(lambda t, f=_fn, d=_vd, c=_cues: f(t, d, c), duration=_vd)
        audio = AudioFileClip(audio_paths[i]).with_start(0.5)
        clip  = clip.with_audio(audio)
        scene_clips.append(clip)

    print(f"\nTotal video: {total_dur:.1f}s")

    # 3 ── Concatenate scenes
    print("Concatenating...")
    final = concatenate_videoclips(scene_clips, method="compose")

    # 4 ── Generate and mix background music
    print("Synthesising background music...")
    music_path = generate_music(total_dur + 2.0, tmp_dir)
    music      = AudioFileClip(music_path)
    if music.duration > final.duration:
        try:
            music = music.subclipped(0, final.duration)
        except AttributeError:
            music = music.subclip(0, final.duration)

    # Mix narration (from scene clips) + background music
    existing_audio = final.audio
    mixed_audio    = CompositeAudioClip([existing_audio, music])
    final          = final.with_audio(mixed_audio)

    # 5 ── Render
    frame_count = int(final.duration * FPS)
    print(f"\nRendering {out_path}")
    print(f"({frame_count} frames at {FPS} fps - please wait...)\n")
    final.write_videofile(
        out_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        logger="bar",
    )

    sz = os.path.getsize(out_path) / 1_048_576
    print(f"\nDone: {out_path}  ({sz:.1f} MB, {total_dur:.0f}s)")


if __name__ == "__main__":
    main()
