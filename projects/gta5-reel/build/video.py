"""Video build for the GTA 5 reel: 1080x1920, 30 fps, fit-width talking head on a brand background.

Usage:
  python3 video.py --dump 0,3,30      write PNG frames to ../work/qa/
  python3 video.py --render           write ../work/video_silent.mp4
  python3 video.py --mux OUT.mp4      mux ../work/audio_final.wav into the silent video
"""
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as T

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "..", "work")
SRC = os.path.join(HERE, "..", "raw", "WhatsApp Video 2026-10-10 at 3.22.45 PM.mp4")
FONT_BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"   # fallback for Anton/Montserrat Black
W, H, FPS = T.W, T.H, T.FPS

CYAN, YELLOW, PURPLE = (0, 198, 255), (255, 215, 0), (127, 0, 255)
WHITE = (255, 255, 255)
COL = {"cyan": CYAN, "yellow": YELLOW, "purple": PURPLE, "white": WHITE}

SRC_W, SRC_H = 368, 496
PW = W
PH = int(round(W * SRC_H / SRC_W))          # 1456
PY0 = (H - PH) // 2                         # 232
PY1 = PY0 + PH
ZOOM_ORIGIN = (0.5, 0.30)
CAPTION_Y = 1395

rng = np.random.default_rng(11)


# ----------------------------------------------------------------------------------------
# Motion helpers
# ----------------------------------------------------------------------------------------
def spring(t, zeta=0.55, wn=18.8):
    """0 -> 1 with ~12% overshoot, settles in ~0.4 s."""
    if t <= 0:
        return 0.0
    wd = wn * math.sqrt(1 - zeta ** 2)
    return 1 - math.exp(-zeta * wn * t) * (math.cos(wd * t) + zeta * wn / wd * math.sin(wd * t))


def ease_out(u):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


def ease_in(u, p=2.2):
    return min(max(u, 0.0), 1.0) ** p


def life(t, t_in, t_out, exit_dur=0.10, pop_from=0.55):
    """Spring-scale entry, quick scale/alpha exit. Returns (scale, alpha) or None if hidden."""
    if t < t_in or t > t_out + exit_dur:
        return None
    s = pop_from + (1 - pop_from) * spring(t - t_in)
    a = min(1.0, (t - t_in) / 0.05)
    if t > t_out:
        u = (t - t_out) / exit_dur
        s *= 1 - 0.15 * u
        a *= 1 - u
    return s, a


def zoom_at(t):
    f0 = T.FLICK[0]
    if t < 2.0:
        return 1.0 + 0.05 * ease_out(t / 2.0)                    # hook push-in 1.00 -> 1.05
    if t < 3.2:
        return 1.05 + 0.02 * (t - 2.0) / 1.2
    if t < 3.2 + 2 / FPS:
        return 1.07 + 0.04 * ease_out((t - 3.2) / (2 / FPS))     # 2-frame punch-in
    if t < f0:
        return 1.11 + 0.02 * (t - 3.2 - 2 / FPS) / (f0 - 3.2 - 2 / FPS)
    if t < f0 + 0.10:
        return 1.13 - 0.13 * ease_out((t - f0) / 0.10)            # snap back on the flick
    if t < 190 / FPS:
        return 1.0 + 0.03 * (t - f0 - 0.10) / (190 / FPS - f0 - 0.10)
    if t < 273 / FPS:                                              # B: punch-in cut
        return 1.09 + 0.02 * (t - 190 / FPS) / (83 / FPS)
    if t < T.END_START_F / FPS:                                    # C: wide so the palm stays in frame
        return 1.0 + 0.03 * (t - 273 / FPS) / (54 / FPS)
    return 1.02 + 0.07 * (t - T.END_START_F / FPS) / (3.1)         # end card: slow push


def shake(t, t0, amp=9.0, dur=0.22):
    d = t - t0
    if d < 0 or d > dur:
        return 0.0, 0.0
    k = amp * math.exp(-d / 0.06)
    return k * math.sin(d * 70), k * 0.6 * math.cos(d * 63)


# ----------------------------------------------------------------------------------------
# Sprites (premultiplied float32 RGBA)
# ----------------------------------------------------------------------------------------
def font(size):
    return ImageFont.truetype(FONT_BOLD, int(size))


def to_premult(img):
    a = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a


def over(dst, src):
    """Premultiplied alpha-over of equal-size float RGBA arrays."""
    return src + dst * (1 - src[..., 3:4])


def text_sprite(words, size, max_w, allow_wrap=True, stroke_ratio=0.09, line_gap=0.98):
    toks = [(wd, col) for text, col in words for wd in text.split(" ")]
    while True:
        f = font(size)
        space = f.getlength(" ")
        lines, lw = [[]], [0.0]
        for wd, col in toks:
            w = f.getlength(wd)
            add = w if not lines[-1] else space + w
            if lw[-1] + add <= max_w or not lines[-1]:
                lines[-1].append((wd, col, w))
                lw[-1] += add
            elif allow_wrap:
                lines.append([(wd, col, w)])
                lw.append(w)
            else:
                lines[-1].append((wd, col, w))
                lw[-1] += add
        if max(lw) <= max_w or size <= 36:
            break
        size -= 4
    stroke = max(3, int(round(size * stroke_ratio)))
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * line_gap)
    pad = stroke + 46
    cw, ch = int(max(lw)) + 2 * pad, lh * len(lines) + 2 * pad
    fill_l = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(fill_l)
    mask = Image.new("L", (cw, ch), 0)
    dm = ImageDraw.Draw(mask)
    for li, line in enumerate(lines):
        x = pad + (max(lw) - lw[li]) / 2
        base = pad + li * lh + asc
        for wd, col, w in line:
            d.text((x, base), wd, font=f, fill=COL[col] + (255,), anchor="ls",
                   stroke_width=stroke, stroke_fill=(PURPLE if col != "cyan" else (58, 0, 138)) + (255,))
            dm.text((x, base), wd, font=f, fill=255, anchor="ls", stroke_width=stroke)
            x += w + space
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(9)).point(lambda v: int(v * 0.6)))
    shadow = ImageChops_offset(shadow, 0, 10)
    glow = Image.new("RGBA", (cw, ch), PURPLE + (0,))
    glow.putalpha(mask.filter(ImageFilter.GaussianBlur(20)).point(lambda v: min(255, int(v * 0.95))))
    out = Image.alpha_composite(Image.alpha_composite(shadow, glow), fill_l)
    return to_premult(out)


def ImageChops_offset(img, dx, dy):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy))
    return out


def stack(sprites, gap=0):
    w = max(s.shape[1] for s in sprites)
    h = sum(s.shape[0] for s in sprites) + gap * (len(sprites) - 1)
    out = np.zeros((h, w, 4), np.float32)
    y = 0
    for s in sprites:
        x = (w - s.shape[1]) // 2
        region = out[y:y + s.shape[0], x:x + s.shape[1]]
        out[y:y + s.shape[0], x:x + s.shape[1]] = over(region, s)
        y += s.shape[0] + gap
    return out


def gradient_img(size, c0, c1, horizontal=True):
    w, h = size
    t = np.linspace(0, 1, w if horizontal else h, dtype=np.float32)
    ramp = np.array(c0, np.float32) * (1 - t[:, None]) + np.array(c1, np.float32) * t[:, None]
    arr = np.broadcast_to(ramp[None] if horizontal else ramp[:, None], (h, w, 3))
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def card_base(w, h, radius=40, border=7, pad=50):
    """Dark rounded card with a cyan->purple gradient border and a purple glow."""
    cw, ch = w + 2 * pad, h + 2 * pad
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    m_out = rounded_mask((w, h), radius)
    glow = Image.new("RGBA", (cw, ch), PURPLE + (0,))
    gm = Image.new("L", (cw, ch), 0)
    gm.paste(m_out, (pad, pad))
    glow.putalpha(gm.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.9)))
    out = Image.alpha_composite(out, glow)
    border_img = gradient_img((w, h), CYAN, PURPLE, horizontal=False).convert("RGBA")
    border_img.putalpha(m_out)
    out.alpha_composite(border_img, (pad, pad))
    inner = gradient_img((w - 2 * border, h - 2 * border), (40, 10, 92), (14, 4, 40), horizontal=False).convert("RGBA")
    inner.putalpha(rounded_mask((w - 2 * border, h - 2 * border), radius - border))
    out.alpha_composite(inner, (pad + border, pad + border))
    return out, pad


def pc_card():
    w, h = 290, 360
    img, pad = card_base(w, h)
    d = ImageDraw.Draw(img)
    ox, oy = pad, pad
    # monitor
    mx0, my0, mx1, my1 = ox + 45, oy + 50, ox + w - 45, oy + 175
    d.rounded_rectangle([mx0, my0, mx1, my1], radius=14, outline=CYAN + (255,), width=9, fill=(12, 2, 34, 255))
    d.rectangle([mx0 + 22, my0 + 24, mx0 + 105, my0 + 34], fill=PURPLE + (255,))
    d.rectangle([mx0 + 22, my0 + 48, mx0 + 150, my0 + 58], fill=CYAN + (200,))
    d.rectangle([mx0 + 22, my0 + 72, mx0 + 80, my0 + 82], fill=YELLOW + (230,))
    d.rectangle([ox + w // 2 - 14, my1, ox + w // 2 + 14, my1 + 30], fill=CYAN + (255,))
    d.rounded_rectangle([ox + w // 2 - 55, my1 + 28, ox + w // 2 + 55, my1 + 42], radius=7, fill=CYAN + (255,))
    # label
    f = font(58)
    d.text((ox + w / 2, oy + h - 62), "PC PLAN", font=f, fill=WHITE + (255,), anchor="mm",
           stroke_width=6, stroke_fill=PURPLE + (255,))
    # yellow cross badge
    cx, cy, r = ox + w - 22, oy + 22, 40
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=YELLOW + (255,), outline=PURPLE + (255,), width=6)
    d.line([cx - 16, cy - 16, cx + 16, cy + 16], fill=(40, 8, 90, 255), width=10)
    d.line([cx - 16, cy + 16, cx + 16, cy - 16], fill=(40, 8, 90, 255), width=10)
    return to_premult(img)


def phone_card():
    w, h = 270, 430
    img, pad = card_base(w, h, radius=46)
    d = ImageDraw.Draw(img)
    ox, oy = pad, pad
    sx0, sy0, sx1, sy1 = ox + 28, oy + 34, ox + w - 28, oy + h - 34
    scr = gradient_img((sx1 - sx0, sy1 - sy0), (127, 0, 255), (0, 120, 200), horizontal=False).convert("RGBA")
    scr.putalpha(rounded_mask(scr.size, 26))
    img.alpha_composite(scr, (sx0, sy0))
    d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=26, outline=CYAN + (255,), width=6)
    d.rounded_rectangle([ox + w / 2 - 34, sy0 + 12, ox + w / 2 + 34, sy0 + 24], radius=6, fill=(10, 2, 30, 255))
    f = font(74)
    d.text((ox + w / 2, oy + h / 2 - 30), "GTA", font=f, fill=YELLOW + (255,), anchor="mm",
           stroke_width=7, stroke_fill=(50, 0, 120, 255))
    d.text((ox + w / 2, oy + h / 2 + 46), "5", font=font(96), fill=YELLOW + (255,), anchor="mm",
           stroke_width=8, stroke_fill=(50, 0, 120, 255))
    # check badge
    cx, cy, r = ox + w - 18, oy + h - 40, 42
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CYAN + (255,), outline=PURPLE + (255,), width=6)
    d.line([cx - 18, cy + 2, cx - 4, cy + 16, cx + 20, cy - 14], fill=(10, 2, 40, 255), width=11, joint="curve")
    return to_premult(img)


def brand_tag(size=36, pad_x=34, pad_y=18, dot=True):
    text = "THE XAAD UNIVERSE"
    f = font(size)
    track = 4
    tw = sum(f.getlength(c) + track for c in text) - track
    icon = 44 if dot else 0
    w, h = int(tw + 2 * pad_x + icon), int(size * 1.25 + 2 * pad_y)
    pad = 36
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    gm = Image.new("L", img.size, 0)
    gm.paste(rounded_mask((w, h), h // 2), (pad, pad))
    glow = Image.new("RGBA", img.size, CYAN + (0,))
    glow.putalpha(gm.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.55)))
    img = Image.alpha_composite(img, glow)
    body = Image.new("RGBA", (w, h), (18, 2, 46, 235))
    body.putalpha(rounded_mask((w, h), h // 2).point(lambda v: int(v * 0.93)))
    img.alpha_composite(body, (pad, pad))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([pad, pad, pad + w - 1, pad + h - 1], radius=h // 2, outline=CYAN + (255,), width=4)
    x = pad + pad_x
    if dot:
        cy = pad + h / 2
        d.polygon([(x + 14, cy - 15), (x + 29, cy), (x + 14, cy + 15), (x, cy)], fill=YELLOW + (255,))
        x += icon
    for c in text:
        d.text((x, pad + h / 2), c, font=f, fill=WHITE + (255,), anchor="lm")
        x += f.getlength(c) + track
    return to_premult(img)


# ----------------------------------------------------------------------------------------
# Compositing
# ----------------------------------------------------------------------------------------
def _M(spr_shape, cx, cy, scale, rot):
    h, w = spr_shape[:2]
    ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    M = np.array([[scale * ca, -scale * sa, 0.0], [scale * sa, scale * ca, 0.0]], np.float32)
    M[0, 2] = cx - (M[0, 0] * w / 2 + M[0, 1] * h / 2)
    M[1, 2] = cy - (M[1, 0] * w / 2 + M[1, 1] * h / 2)
    return M


def _bbox(spr_shape, M):
    h, w = spr_shape[:2]
    c = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], np.float32) @ M.T
    return (int(math.floor(c[:, 0].min())) - 1, int(math.floor(c[:, 1].min())) - 1,
            int(math.ceil(c[:, 0].max())) + 1, int(math.ceil(c[:, 1].max())) + 1)


def blit(canvas, spr, cx, cy, scale=1.0, rot=0.0, alpha=1.0, mb=None):
    """Composite a premultiplied sprite. mb = list of (cx, cy, scale, rot) sub-samples for motion blur."""
    samples = mb if mb else [(cx, cy, scale, rot)]
    Ms = [_M(spr.shape, *s) for s in samples]
    boxes = [_bbox(spr.shape, M) for M in Ms]
    x0 = max(min(b[0] for b in boxes), 0)
    y0 = max(min(b[1] for b in boxes), 0)
    x1 = min(max(b[2] for b in boxes), canvas.shape[1])
    y1 = min(max(b[3] for b in boxes), canvas.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    acc = np.zeros((y1 - y0, x1 - x0, 4), np.float32)
    for M in Ms:
        M2 = M.copy()
        M2[0, 2] -= x0
        M2[1, 2] -= y0
        acc += cv2.warpAffine(spr, M2, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    acc /= len(Ms)
    a = acc[..., 3:4] * alpha
    roi = canvas[y0:y1, x0:x1]
    roi[:] = roi * (1 - a) + acc[..., :3] * alpha


def add_ring(canvas, cx, cy, r, th, color, alpha):
    if alpha <= 0.01:
        return
    m = np.zeros(canvas.shape[:2], np.float32)
    cv2.circle(m, (int(cx), int(cy)), int(r), 1.0, thickness=int(th), lineType=cv2.LINE_AA)
    m = cv2.GaussianBlur(m, (0, 0), 2.0)
    canvas += m[..., None] * (np.array(color, np.float32) / 255.0) * alpha


# ----------------------------------------------------------------------------------------
# Asset cache
# ----------------------------------------------------------------------------------------
class Assets:
    def __init__(self):
        self.bg = self._bg_base()
        self.orb_p = self._orb(430)
        self.orb_c = self._orb(380)
        yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
        d = np.sqrt(((xx - PW / 2) / (PW / 2)) ** 2 + ((yy - PH / 2) / (PH / 2)) ** 2)
        self.vig = (1 - 0.16 * np.clip(d - 0.55, 0, 1) ** 1.5)[..., None].astype(np.float32)
        # sprites
        self.hook = stack([
            text_sprite([("GTA 5 ON YOUR PHONE", "yellow")], 72, 980, allow_wrap=False),
            text_sprite([("NO PC!", "cyan")], 170, 980, allow_wrap=False),
        ], gap=-30)
        self.tag = brand_tag(36)
        self.tag_big = brand_tag(46, 40, 22)
        self.pc = pc_card()
        self.phone = phone_card()
        self.captions = []
        for words, on, off in T.CAPTIONS:
            txt = " ".join(t for t, _ in words)
            if txt.startswith("JHERE"):
                spr = stack([text_sprite([("JHERE FELE", "yellow")], 124, 930, allow_wrap=False),
                             text_sprite([("DAO!", "cyan")], 168, 930, allow_wrap=False)], gap=-112)
            elif txt.startswith("GTA 5!"):
                spr = text_sprite(words, 156, 930, allow_wrap=False)
            else:
                spr = text_sprite(words, 106, 930, allow_wrap=True)
            self.captions.append(spr)
        self.end1 = text_sprite([("FOLLOW FOR MORE", "yellow")], 104, 880, allow_wrap=False)
        self.end2 = text_sprite([("GAMING TIPS!", "cyan")], 160, 880, allow_wrap=False)
        self.top_shade = self._shade()
        self.bot_shade = self._shade_bottom()
        self.edge = self._edge()

    @staticmethod
    def _bg_base():
        y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
        top, mid, bot = (np.array(c, np.float32) / 255 for c in ((46, 12, 104), (24, 5, 62), (7, 0, 24)))
        col = np.where(y < 0.5, top + (mid - top) * (y / 0.5), mid + (bot - mid) * ((y - 0.5) / 0.5))
        base = np.broadcast_to(col, (H, W, 3)).astype(np.float32).copy()
        base[::4] *= 0.955
        return base

    @staticmethod
    def _orb(r):
        yy, xx = np.mgrid[-r:r, -r:r].astype(np.float32)
        d = np.sqrt(xx ** 2 + yy ** 2) / r
        return (np.exp(-(d ** 2) * 6.0) * np.clip(1.15 - d, 0, 1)).astype(np.float32)[..., None]

    @staticmethod
    def _shade():
        h = 340
        a = np.linspace(0.72, 0, h, dtype=np.float32) ** 1.4
        spr = np.zeros((h, W, 4), np.float32)
        spr[..., 3] = a[:, None]
        spr[..., 0], spr[..., 1], spr[..., 2] = 18 / 255 * a[:, None], 0, 46 / 255 * a[:, None]
        return spr

    @staticmethod
    def _shade_bottom():
        h = 460
        a = (np.linspace(0, 1, h, dtype=np.float32) ** 1.6) * 0.55
        spr = np.zeros((h, W, 4), np.float32)
        spr[..., 3] = a[:, None]
        spr[..., 0], spr[..., 1], spr[..., 2] = 10 / 255 * a[:, None], 0, 30 / 255 * a[:, None]
        return spr

    @staticmethod
    def _edge():
        h = 70
        line = gradient_img((W, 7), CYAN, PURPLE).convert("RGBA")
        spr = Image.new("RGBA", (W, h), (0, 0, 0, 0))
        glow = Image.new("RGBA", (W, h), CYAN + (0,))
        gm = Image.new("L", (W, h), 0)
        ImageDraw.Draw(gm).rectangle([0, h // 2 - 3, W, h // 2 + 3], fill=255)
        glow.putalpha(gm.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.55)))
        spr = Image.alpha_composite(spr, glow)
        spr.alpha_composite(line, (0, h // 2 - 3))
        return to_premult(spr)


# ----------------------------------------------------------------------------------------
# Frame renderer
# ----------------------------------------------------------------------------------------
class Renderer:
    def __init__(self):
        self.a = Assets()
        self.frames = self._load_source()

    def _load_source(self):
        cmd = ["ffmpeg", "-v", "error", "-i", SRC, "-vf", "fps=30", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        n = len(raw) // (SRC_W * SRC_H * 3)
        arr = np.frombuffer(raw, np.uint8)[: n * SRC_W * SRC_H * 3].reshape(n, SRC_H, SRC_W, 3)
        return arr

    def _clean_src(self, idx):
        cache = getattr(self, "_cs", None)
        if cache is None:
            cache = self._cs = {}
        if idx not in cache:
            cache[idx] = cv2.fastNlMeansDenoisingColored(np.ascontiguousarray(self.frames[idx]), None, 3, 3, 5, 15)
        return cache[idx]

    def panel(self, src_idx, zoom, dx=0.0, dy=0.0):
        src = self._clean_src(src_idx)
        ox, oy = ZOOM_ORIGIN[0] * PW, ZOOM_ORIGIN[1] * PH
        sx, sy = PW / SRC_W * zoom, PH / SRC_H * zoom
        M = np.array([[sx, 0, ox - ox * zoom + dx], [0, sy, oy - oy * zoom + dy]], np.float32)
        img = cv2.warpAffine(src, M, (PW, PH), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        img = img.astype(np.float32) / 255.0
        blur = cv2.GaussianBlur(img, (0, 0), 1.6)
        img = img * 1.45 - blur * 0.45                                   # unsharp: recover softness from the upscale
        img = (img - 0.5) * 1.07 + 0.5                                   # contrast
        gray = img.mean(2, keepdims=True)
        img = gray + (img - gray) * 1.10                                 # saturation
        img *= self.a.vig
        img += rng.standard_normal((PH, PW, 1)).astype(np.float32) * 0.011   # fine grain hides compression
        return np.clip(img, 0, 1)

    def background(self, t):
        c = self.a.bg.copy()
        for orb, col, cx, cy in (
            (self.a.orb_p, PURPLE, 880 + 70 * math.sin(t * 0.7), 150 + 40 * math.cos(t * 0.5)),
            (self.a.orb_c, CYAN, 190 + 60 * math.cos(t * 0.55), 1790 + 40 * math.sin(t * 0.8)),
            (self.a.orb_p, PURPLE, 230 + 50 * math.sin(t * 0.4), 1700),
        ):
            r = orb.shape[0] // 2
            x0, y0 = int(cx) - r, int(cy) - r
            xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + 2 * r, W), min(y0 + 2 * r, H)
            if xb > xa and yb > ya:
                o = orb[ya - y0:yb - y0, xa - x0:xb - x0]
                c[ya:yb, xa:xb] += o * (np.array(col, np.float32) / 255.0) * 0.40
        return c

    def render(self, i):
        t = i / FPS
        a = self.a
        canvas = self.background(t)
        end_k = min(max((t - T.END_START_F / FPS) / 0.25, 0), 1)

        sx = sy = 0.0
        for t0, amp in ((T.HOOK_IN, 8.0), (190 / FPS, 6.0), (T.END_START_F / FPS, 8.0)):
            ddx, ddy = shake(t, t0, amp)
            sx, sy = sx + ddx, sy + ddy

        src_idx = T.out_to_src_frame(i)
        canvas[PY0:PY1] = self.panel(src_idx, zoom_at(t), sx, sy)
        blit(canvas, a.bot_shade, W / 2, PY1 - a.bot_shade.shape[0] / 2, 1.0)
        blit(canvas, a.edge, W / 2, PY0, 1.0)
        blit(canvas, a.edge, W / 2, PY1, 1.0)

        # ---- hook ----------------------------------------------------------------------
        lf = life(t, T.HOOK_IN, T.HOOK_OUT, 0.16)
        if lf:
            s, al = lf
            blit(canvas, a.top_shade, W / 2, PY0 + a.top_shade.shape[0] / 2, 1.0, 0, al * 0.9)
            blit(canvas, a.hook, W / 2, 378, s, 0, al)
        # ---- brand tag -----------------------------------------------------------------
        lf = life(t, T.TAG_IN, T.TAG_OUT, 0.12, pop_from=0.4)
        if lf:
            s, al = lf
            blit(canvas, a.tag, W / 2, 196, s, 0, al)
        # ---- cards ---------------------------------------------------------------------
        self._pc_card(canvas, t)
        lf = life(t, T.PHONE_CARD_IN, T.END_START_F / FPS - 0.04, 0.12, pop_from=0.3)
        if lf:
            s, al = lf
            bob = 5 * math.sin((t - T.PHONE_CARD_IN) * 3.2)
            blit(canvas, a.phone, 902, 500 + bob, s * 0.78, -5, al)
        # ---- captions ------------------------------------------------------------------
        for (words, on, off), spr in zip(T.CAPTIONS, a.captions):
            txt = words[0][0]
            if txt.startswith("JHERE"):
                self._swipe_caption(canvas, spr, t, on)
                continue
            lf = life(t, on, off, 0.08, pop_from=0.62)
            if lf:
                s, al = lf
                blit(canvas, spr, W / 2, CAPTION_Y, s, 0, al)
                if txt.startswith("AJKE"):
                    self._underline(canvas, t, spr, s)
        # ---- impact accents ------------------------------------------------------------
        for t0, col in ((T.HOOK_IN, CYAN),):
            d = t - t0
            if 0 <= d < 0.4:
                add_ring(canvas, W / 2, 380, 120 + 520 * ease_out(d / 0.4), 5 * (1 - d / 0.4) + 2,
                         col, 0.26 * (1 - d / 0.4))
        for t0 in (T.HOOK_IN, 190 / FPS):
            d = t - t0
            if 0 <= d < 0.12:
                canvas += (1 - d / 0.12) * 0.12

        # ---- end card ------------------------------------------------------------------
        if end_k > 0:
            canvas = self._end_card(canvas, t, end_k)
        return np.clip(canvas * 255.0 + 0.5, 0, 255).astype(np.uint8)

    def _pc_card(self, canvas, t):
        a = self.a
        t_in = T.PC_CARD_IN
        f0, f1 = T.FLICK
        if t < t_in or t > f1 + 0.05:
            return
        base = (925, 455, 0.86, 5.0)
        if t < f0:
            lf = life(t, t_in, 99, 0.1, pop_from=0.3)
            s, al = lf
            bob = 5 * math.sin((t - t_in) * 3.0)
            blit(canvas, a.pc, base[0], base[1] + bob, s * base[2], base[3], al)
            return
        samples = self._swipe_samples(t, base[0], base[1], base[2], base[3], f0, f1, extra_rot=18)
        if samples:
            blit(canvas, a.pc, 0, 0, alpha=1.0, mb=samples)

    def _swipe_samples(self, t, cx, cy, s, rot, f0, f1, extra_rot=0.0):
        """Positions along the swipe path across the exposure of this frame (motion-blur sub-samples)."""
        if t > f1 + 0.04:
            return None
        shutter, k = 1.0 / FPS * 0.95, 40
        out = []
        dist = W + 700
        for j in range(k):
            tj = t - shutter * j / (k - 1)
            u = (tj - f0) / (f1 - f0)
            e = ease_in(u, 2.4)
            out.append((cx + dist * e, cy - 60 * e, s, rot + extra_rot * min(max(u, 0), 1.2)))
        if all(o[0] > W + 330 for o in out):
            return None
        return out

    def _swipe_caption(self, canvas, spr, t, on):
        f0, f1 = T.FLICK
        if t < on or t > f1 + 0.05:
            return
        if t < f0:
            lf = life(t, on, 99, 0.1, pop_from=0.62)
            s, al = lf
            blit(canvas, spr, W / 2, CAPTION_Y, s, 0, al)
            return
        samples = self._swipe_samples(t, W / 2, CAPTION_Y, 1.0, 0.0, f0 + 0.02, f1 + 0.04, extra_rot=-6)
        if samples:
            blit(canvas, spr, 0, 0, alpha=1.0, mb=samples)

    def _underline(self, canvas, t, spr, s):
        u = ease_out((t - T.UNDERLINE_IN) / 0.28)
        if u <= 0:
            return
        half = (spr.shape[1] - 92) * 0.9 / 2 * s
        y = int(CAPTION_Y + 74 * s)
        x0, x1 = int(W / 2 - half), int(W / 2 - half + 2 * half * u)
        lay = np.zeros((H, W), np.float32)
        cv2.line(lay, (x0, y), (max(x1, x0 + 1), y), 1.0, 13, cv2.LINE_AA)
        cv2.circle(lay, (x0, y), 6, 1.0, -1, cv2.LINE_AA)
        cv2.circle(lay, (max(x1, x0 + 1), y), 6, 1.0, -1, cv2.LINE_AA)
        glow = cv2.GaussianBlur(lay, (0, 0), 9)
        col = np.array(YELLOW, np.float32) / 255.0
        canvas[:] = canvas * (1 - lay[..., None]) + lay[..., None] * col
        canvas += glow[..., None] * np.array(PURPLE, np.float32) / 255.0 * 0.5

    def _end_card(self, canvas, t, k):
        a = self.a
        small = cv2.resize(canvas, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), 6.0)
        blurred = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
        dark = blurred * 0.38 + np.array(PURPLE, np.float32) / 255.0 * 0.20
        canvas = canvas * (1 - k) + dark * k
        te = t - T.END_START_F / FPS
        for ph in (0.0, 0.9):
            d = (te - ph) % 1.8
            add_ring(canvas, W / 2, 850, 120 + 760 * ease_out(d / 1.8), 5, CYAN if ph == 0 else PURPLE, 0.30 * (1 - d / 1.8))
        if 0 <= te < 0.4:
            add_ring(canvas, W / 2, 850, 100 + 1100 * ease_out(te / 0.4), 10 * (1 - te / 0.4) + 3, YELLOW, 0.6 * (1 - te / 0.4))
        for spr, t_in, y in ((a.end1, T.END_TEXT1_IN, 760), (a.end2, T.END_TEXT2_IN, 960)):
            lf = life(t, t_in, 99, 0.1, pop_from=0.3)
            if lf:
                s, al = lf
                s *= 1 + 0.012 * math.sin(max(t - t_in - 0.5, 0) * 2 * math.pi * 1.6)
                blit(canvas, spr, W / 2, y, s, 0, al)
        lf = life(t, T.END_TAG_IN, 99, 0.1, pop_from=0.4)
        if lf:
            s, al = lf
            blit(canvas, a.tag_big, W / 2, 1230, s, 0, al)
        return canvas


# ----------------------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    r = Renderer()
    os.makedirs(WORK, exist_ok=True)
    if "--dump" in args:
        qa = os.path.join(WORK, "qa")
        os.makedirs(qa, exist_ok=True)
        for tok in args[args.index("--dump") + 1].split(","):
            i = int(tok)
            Image.fromarray(r.render(i)).save(os.path.join(qa, f"f{i:03d}.png"))
            print("wrote", f"f{i:03d}.png")
    if "--render" in args:
        out = os.path.join(WORK, "video_silent.mp4")
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
               "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-maxrate", "14M", "-bufsize", "28M", "-profile:v", "high", "-level", "4.2",
               "-r", str(FPS), "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-movflags", "+faststart", out]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for i in range(T.TOTAL_FRAMES):
            p.stdin.write(r.render(i).tobytes())
            if i % 60 == 0:
                print("frame", i, flush=True)
        p.stdin.close()
        p.wait()
        print("wrote", out)
    if "--mux" in args:
        outp = args[args.index("--mux") + 1]
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(WORK, "video_silent.mp4"),
                        "-i", os.path.join(WORK, "audio_final.wav"), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-shortest", "-movflags", "+faststart", outp], check=True)
        print("wrote", outp)


if __name__ == "__main__":
    main()
