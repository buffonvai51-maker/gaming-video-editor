#!/usr/bin/env python3
"""Step 3: build the picture (layout, graphics, captions, effects) and encode with the final audio.

Usage:
  03_video.py --preview 3,20,45        write PNGs of those output frames to ../work/preview/
  03_video.py out.mp4                  render the full 1080x1920 30fps H.264 video
"""
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import timeline as T

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORK = os.path.join(ROOT, "work")
FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
W, H, FPS = T.W, T.H, T.FPS

CYAN, YELLOW, PURPLE, WHITE = (0, 198, 255), (255, 215, 0), (127, 0, 255), (255, 255, 255)
DEEP = (14, 3, 32)

VID_W, VID_H, VID_Y0 = 1080, 1456, 380
rng = np.random.default_rng(11)


# ---------------------------------------------------------------- helpers
def spring(t, zeta=0.56, w=26.0):
    if t <= 0:
        return 0.0
    wd = w * math.sqrt(1 - zeta ** 2)
    return 1 - math.exp(-zeta * w * t) * (math.cos(wd * t) + zeta / math.sqrt(1 - zeta ** 2) * math.sin(wd * t))


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def font(size):
    return ImageFont.truetype(FONT, size)


def text_size(text, size, stroke):
    b = ImageDraw.Draw(Image.new("L", (4, 4))).textbbox((0, 0), text, font=font(size), stroke_width=stroke)
    return b[2] - b[0], b[3] - b[1], b


def render_word(text, size, fill, stroke=12, stroke_fill=PURPLE, glow=None, pad=44):
    tw, th, b = text_size(text, size, stroke)
    w, h = tw + 2 * pad, th + 2 * pad
    ox, oy = pad - b[0], pad - b[1]
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if glow:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((ox, oy), text, font=font(size), fill=glow + (255,),
                               stroke_width=stroke + 6, stroke_fill=glow + (255,))
        g = g.filter(ImageFilter.GaussianBlur(14))
        g.putalpha(g.getchannel("A").point(lambda v: int(v * 0.85)))
        layer = Image.alpha_composite(layer, g)
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((ox, oy + 9), text, font=font(size), fill=(0, 0, 0, 170),
                            stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
    sh = sh.filter(ImageFilter.GaussianBlur(7))
    layer = Image.alpha_composite(layer, sh)
    ImageDraw.Draw(layer).text((ox, oy), text, font=font(size), fill=fill + (255,),
                               stroke_width=stroke, stroke_fill=stroke_fill + (255,))
    return layer


def join_h(sprites, gap):
    w = sum(s.width for s in sprites) + gap * (len(sprites) - 1)
    h = max(s.height for s in sprites)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for s in sprites:
        out.alpha_composite(s, (x, (h - s.height) // 2))
        x += s.width + gap
    return out


def stack_v(sprites, gap):
    w = max(s.width for s in sprites)
    h = sum(s.height for s in sprites) + gap * (len(sprites) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for s in sprites:
        out.alpha_composite(s, ((w - s.width) // 2, y))
        y += s.height + gap
    return out


def caption_sprite(words, size, max_w=980, **kw):
    """words: [(text, color)]. Shrinks the font until the line fits max_w."""
    while True:
        parts = [render_word(t, size, c, **kw) for t, c in words]
        s = join_h(parts, int(size * 0.24) - 2 * 44)
        if s.width <= max_w or size < 40:
            return s
        size -= 4


def draw_sprite(img, sp, cx, cy, sx=1.0, sy=None, alpha=1.0):
    sy = sx if sy is None else sy
    w, h = max(1, int(sp.width * sx)), max(1, int(sp.height * sy))
    if alpha <= 0 or w < 2 or h < 2:
        return
    s = sp.resize((w, h), Image.BICUBIC) if (w, h) != sp.size else sp
    if alpha < 1.0:
        s = s.copy()
        s.putalpha(s.getchannel("A").point([int(i * alpha) for i in range(256)]))
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(img.width, x0 + w), min(img.height, y0 + h)
    if X1 <= X0 or Y1 <= Y0:
        return
    src = s.crop((X0 - x0, Y0 - y0, X1 - x0, Y1 - y0))
    img.paste(Image.alpha_composite(img.crop((X0, Y0, X1, Y1)), src), (X0, Y0))


def rounded_card(w, h, border=CYAN, radius=34):
    pad = 40
    base = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((pad, pad, pad + w, pad + h), radius, fill=border + (200,))
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    base.alpha_composite(glow)
    grad = Image.new("RGBA", (w, h))
    gp = grad.load()
    for y in range(h):
        k = y / (h - 1)
        c = (int(150 - 90 * k), int(20 - 20 * k), int(255 - 120 * k), 245)
        for x in range(w):
            gp[x, y] = c
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    card.paste(grad, (0, 0), mask)
    ImageDraw.Draw(card).rounded_rectangle((2, 2, w - 3, h - 3), radius, outline=border + (255,), width=5)
    base.alpha_composite(card, (pad, pad))
    return base


def icon_pc(size=100):
    s = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.rounded_rectangle((6, 10, size - 6, size * 0.68), 9, fill=(10, 4, 30, 255), outline=WHITE + (255,), width=5)
    d.rounded_rectangle((16, 20, size - 16, size * 0.58), 4, fill=CYAN + (255,))
    d.rectangle((size / 2 - 7, size * 0.68, size / 2 + 7, size * 0.82), fill=WHITE + (255,))
    d.rounded_rectangle((size * 0.28, size * 0.82, size * 0.72, size * 0.9), 4, fill=WHITE + (255,))
    return s


def icon_phone(size=100):
    s = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    x0, x1 = size * 0.27, size * 0.73
    d.rounded_rectangle((x0, 4, x1, size - 4), 11, fill=(10, 4, 30, 255), outline=WHITE + (255,), width=5)
    d.rounded_rectangle((x0 + 7, 17, x1 - 7, size - 17), 4, fill=(60, 0, 140, 255))
    cx, cy = size / 2, size / 2
    d.polygon([(cx - 8, cy - 13), (cx - 8, cy + 13), (cx + 14, cy)], fill=YELLOW + (255,))
    d.ellipse((cx - 3, 9, cx + 3, 15), fill=WHITE + (255,))
    return s


def icon_play(size=100):
    s = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.ellipse((6, 6, size - 6, size - 6), fill=(10, 4, 30, 255), outline=CYAN + (255,), width=6)
    cx, cy = size / 2 + 3, size / 2
    d.polygon([(cx - 14, cy - 20), (cx - 14, cy + 20), (cx + 22, cy)], fill=YELLOW + (255,))
    return s


def make_card(icon, parts, w=640, h=132):
    base = rounded_card(w, h)
    pad = 40
    ic = icon(96)
    base.alpha_composite(ic, (pad + 26, pad + (h - 96) // 2))
    txt = join_h([render_word(t, 62, c, stroke=8, pad=10) for t, c in parts], -6)
    base.alpha_composite(txt, (pad + 26 + 96 + 14, pad + (h - txt.height) // 2))
    return base


def brand_pill():
    t = render_word("THE XAAD UNIVERSE", 42, WHITE, stroke=0, pad=4)
    w, h, pad = t.width + 120, 76, 30
    base = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    g = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).rounded_rectangle((pad, pad, pad + w, pad + h), h // 2, fill=CYAN + (170,))
    base.alpha_composite(g.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), h // 2, fill=(20, 0, 50, 235), outline=CYAN + (255,), width=4)
    d.ellipse((pad + 26, pad + h / 2 - 10, pad + 46, pad + h / 2 + 10), fill=YELLOW + (255,))
    base.alpha_composite(t, (pad + 70, pad + (h - t.height) // 2))
    return base


# ---------------------------------------------------------------- backgrounds
def make_background():
    yy = np.linspace(0, 1, H)[:, None, None]
    top, bot = np.array([70, 0, 150]), np.array([10, 2, 28])
    bg = (top * (1 - yy) + bot * yy) * np.ones((1, W, 1))
    cy, cx = 560, W / 2
    Y, X = np.mgrid[0:H, 0:W]
    r = np.sqrt(((X - cx) / 700) ** 2 + ((Y - cy) / 900) ** 2)
    bg += np.clip(1 - r, 0, 1)[..., None] ** 2 * np.array([60, 20, 110])
    return bg.astype(np.float32)


def make_streaks():
    """Soft diagonal light bands that scroll slowly; RGBA float, tall enough to wrap."""
    th = H + 800
    img = Image.new("RGBA", (W, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(10):
        x = rng.integers(-200, W + 200)
        wd = int(rng.integers(30, 110))
        col = CYAN if i % 3 else PURPLE
        d.polygon([(x, 0), (x + wd, 0), (x + wd - 380, th), (x - 380, th)], fill=col + (int(rng.integers(14, 30)),))
    img = img.filter(ImageFilter.GaussianBlur(10))
    return np.asarray(img).astype(np.float32)


# ---------------------------------------------------------------- picture
class Build:
    def __init__(self):
        cache = os.path.join(WORK, "denoised.npy")
        if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(os.path.join(WORK, "cut_src.mp4")):
            self.src = list(np.load(cache))
        else:
            cap = cv2.VideoCapture(os.path.join(WORK, "cut_src.mp4"))
            self.src = []
            while True:
                ok, fr = cap.read()
                if not ok:
                    break
                self.src.append(cv2.fastNlMeansDenoisingColored(fr, None, 3, 3, 5, 15))
            np.save(cache, np.stack(self.src))
        assert len(self.src) == T.SPEECH_FRAMES + T.TAIL_SRC_FRAMES, len(self.src)
        self.bg = make_background()
        self.streak = make_streaks()
        self.grain_seed = 0

        self.hook = stack_v([
            caption_sprite([("GTA", CYAN), ("5", YELLOW), ("ON", WHITE), ("PHONE", YELLOW)], 150, 1010, stroke=14, glow=PURPLE),
            caption_sprite([("NO", CYAN), ("PC", CYAN), ("NEEDED", WHITE)], 96, 820, stroke=10, glow=PURPLE),
        ], -52)
        self.brand = brand_pill()
        self.pc_card = make_card(icon_pc, [("PC", CYAN), ("PLAN", YELLOW)])
        self.see_card = make_card(icon_play, [("SEE", WHITE), ("HOW", YELLOW)], w=520)
        self.phone_card = make_card(icon_phone, [("GTA 5", YELLOW), ("ON", WHITE), ("PHONE", CYAN)], w=720)

        c = {"GTA 5": [("GTA", CYAN), ("5", YELLOW)],
             "PC KENAR PLAN": [("PC", CYAN), ("KENAR", YELLOW), ("PLAN", YELLOW)],
             "MATHA THEKE": [("MATHA", YELLOW), ("THEKE", YELLOW)],
             "JHERE FELE DAO!": [("JHERE", CYAN), ("FELE", YELLOW), ("DAO!", YELLOW)],
             "AJKE DEKHABO": [("AJKE", YELLOW), ("DEKHABO", CYAN)],
             "KIBHABE": [("KIBHABE", YELLOW)],
             "SMARTPHONE E": [("SMARTPHONE", CYAN), ("E", YELLOW)],
             "PLAY KORBA": [("PLAY", CYAN), ("KORBA", YELLOW)]}
        self.caps = []
        for text, s, e, style in T.CAPTIONS:
            size = {"normal": 104, "hero": 116, "slam": 124}[style]
            sp = caption_sprite(c[text], size, 980, stroke=12, glow=PURPLE if style != "slam" else CYAN)
            self.caps.append((sp, T.src2out(s), T.src2out(e - 0.001), style))

        self.cta = [
            (caption_sprite([("FOLLOW", YELLOW)], 210, 980, stroke=16, glow=CYAN), 800, 0.10),
            (caption_sprite([("FOR", WHITE), ("MORE", WHITE)], 96, 980, stroke=10, glow=PURPLE), 972, 0.20),
            (caption_sprite([("GAMING", CYAN), ("TIPS!", YELLOW)], 130, 980, stroke=12, glow=PURPLE), 1120, 0.30),
        ]

    # ---- zoom plan (output seconds -> scale)
    def zoom(self, t):
        A_END, B0, B1 = 106 / FPS, 106 / FPS, 180 / FPS
        C0, C1 = 180 / FPS, 262 / FPS
        D0, D1 = 262 / FPS, T.END_IN
        if t < A_END:
            z = 1 + 0.05 * ease_out(t / 2.0)
            if t > 2.0:
                z = 1.05 - 0.02 * (t - 2.0) / (A_END - 2.0)
        elif t < B1:
            z = 1.0 + 0.035 * ease_io((t - B0) / (T.SWIPE_START - B0)) if t < T.SWIPE_START else \
                1.035 + 0.04 * ease_out((t - T.SWIPE_START) / (T.SWIPE_END - T.SWIPE_START))
        elif t < C1:
            z = 1.05 - 0.05 * ease_out((t - C0) / 1.2)
            if t > C0 + 1.2:
                z = 1.0 + 0.03 * (t - C0 - 1.2) / (C1 - C0 - 1.2)
        elif t < D1:
            z = 1.0 + 0.06 * ease_io((t - D0) / (D1 - D0))
        else:
            z = 1.06 + 0.04 * ease_io((t - D1) / (T.TOTAL_FRAMES / FPS - D1))
        ph = (t - T.BEAT0) % T.BEAT
        lull = T.BEAT0 + 10 * T.BEAT <= t < T.BEAT0 + 11 * T.BEAT
        if t >= T.BEAT0 and not lull:
            z *= 1 + 0.006 * math.exp(-ph * 9)
        return z

    def video_layer(self, f, t):
        fr = self.src[min(f, len(self.src) - 1)]
        z = self.zoom(t)
        s = (VID_W / T.SRC_SIZE[0]) * z
        M = np.float32([[s, 0, VID_W / 2 - s * T.SRC_SIZE[0] / 2],
                        [0, s, VID_H / 2 - s * T.SRC_SIZE[1] / 2 - 4]])
        v = cv2.warpAffine(fr, M, (VID_W, VID_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        v = v.astype(np.float32)
        blur = cv2.GaussianBlur(v, (0, 0), 2.4)
        v = v * 1.55 - blur * 0.55                       # unsharp: restore edge definition after 2.9x upscale
        v = (v - 128) * 1.07 + 128                       # contrast
        gray = v.mean(axis=2, keepdims=True)
        v = gray + (v - gray) * 1.12                     # saturation
        v += (1 - np.clip(v, 0, 255) / 255) * np.array([22, 0, 10]) * 0.30   # BGR: faint purple in shadows
        g = rng.normal(0, 3.4, (VID_H // 2, VID_W // 2, 1)).astype(np.float32)
        v += cv2.resize(g, (VID_W, VID_H), interpolation=cv2.INTER_LINEAR)[..., None]
        yy, xx = np.mgrid[0:VID_H, 0:VID_W]
        r = np.sqrt(((xx - VID_W / 2) / (VID_W * 0.75)) ** 2 + ((yy - VID_H / 2) / (VID_H * 0.75)) ** 2)
        v *= (1 - 0.22 * np.clip(r - 0.35, 0, 1) ** 1.5)[..., None]
        if t >= T.END_IN:
            k = ease_io((t - T.END_IN) / 0.25)
            v = cv2.GaussianBlur(v, (0, 0), 0.1 + 11 * k)
            v *= 1 - 0.55 * k
        return np.clip(v, 0, 255)[..., ::-1]             # BGR -> RGB

    def canvas(self, f, t):
        ph = (t - T.BEAT0) % T.BEAT
        pulse = 1 + 0.18 * math.exp(-ph * 7) if t >= T.BEAT0 else 1.0
        bg = self.bg * pulse
        off = int(f * 5) % 800
        st = self.streak[off:off + H]
        a = st[..., 3:4] / 255.0
        bg = bg * (1 - a) + st[..., :3] * a * 2.2
        out = bg.copy()
        out[VID_Y0:VID_Y0 + VID_H] = self.video_layer(f, t)
        # neon edges around the video window
        for y, col in ((VID_Y0 - 3, CYAN), (VID_Y0 + VID_H, YELLOW)):
            out[y:y + 6] = np.array(col, np.float32)
            glow = out[max(0, y - 14):y + 20].copy()
            out[max(0, y - 14):y + 20] = cv2.addWeighted(glow, 0.8, cv2.GaussianBlur(glow, (0, 0), 6), 0.4, 0)
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")

    def overlay_flash(self, img, strength, color=CYAN):
        if strength <= 0.01:
            return
        layer = Image.new("RGBA", (W, VID_H), color + (int(255 * min(1, strength)),))
        img.alpha_composite(layer, (0, VID_Y0))

    def card_pos_y(self):
        return 318

    def swipe_card(self, img, t):
        """Motion-blurred swipe-off of the PC card, synced to the hand swipe (+x in the source)."""
        sp = self.pc_card
        cx0, cy = W / 2, self.card_pos_y()
        dur = T.SWIPE_END - T.SWIPE_START
        band_h = sp.height + 60
        y0 = int(cy - band_h / 2)
        K, shutter = 18, 0.8 / FPS
        acc = np.zeros((band_h, W, 4), np.float32)
        for k in range(K):
            ts = t - shutter * k / (K - 1)
            u = (ts - T.SWIPE_START) / dur
            if u < 0:
                x, sx, sy = cx0 + 14 * u * 4, 1.0, 1.0           # tiny anticipation
            elif u > 1.4:
                continue
            else:
                x = cx0 + (W / 2 + sp.width / 2 + 160) * (u ** 2.3)
                sx, sy = 1.0 + 0.14 * min(1, u), 1.0 - 0.06 * min(1, u)
            tmp = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
            draw_sprite(tmp, sp, x, band_h / 2, sx, sy)
            a = np.asarray(tmp).astype(np.float32)
            acc += np.concatenate([a[..., :3] * (a[..., 3:4] / 255.0), a[..., 3:4]], axis=2)
        acc /= K
        dest = np.asarray(img.crop((0, y0, W, y0 + band_h))).astype(np.float32)
        al = acc[..., 3:4] / 255.0
        out = acc[..., :3] + dest[..., :3] * (1 - al)
        res = np.concatenate([out, np.full_like(al, 255)], axis=2).clip(0, 255).astype(np.uint8)
        img.paste(Image.fromarray(res, "RGBA"), (0, y0))
        # speed streaks trailing the card
        u = (t - T.SWIPE_START) / dur
        if 0 <= u <= 1.4:
            d = ImageDraw.Draw(img, "RGBA")
            xh = cx0 + (W / 2 + sp.width / 2 + 160) * (max(0, u) ** 2.3)
            for i in range(12):
                yy = cy + rng.integers(-62, 62)
                ln = rng.integers(260, 620)
                d.line([(xh - sp.width / 2 - ln, yy), (xh - sp.width / 2, yy)],
                       fill=(CYAN if i % 2 else WHITE) + (int(rng.integers(70, 150)),), width=int(rng.integers(3, 7)))

    def render(self, f):
        t = f / FPS
        img = self.canvas(f, t)

        # hook title
        if T.HOOK_IN <= t < T.HOOK_OUT + 0.25:
            lt = t - T.HOOK_IN
            sc = spring(lt)
            al = min(1, lt / 0.06)
            ex = (t - T.HOOK_OUT) / 0.25
            if ex > 0:
                sc *= 1 - 0.25 * ease_io(ex)
                al *= 1 - ease_io(ex)
            draw_sprite(img, self.hook, W / 2, 255 - 22 * max(0, ex), sc, alpha=al)

        # brand pill
        if t >= T.BRAND_IN:
            lt = t - T.BRAND_IN
            draw_sprite(img, self.brand, W / 2, 204, spring(lt), alpha=min(1, lt / 0.06))

        # PC card (in at "PC kenar plan", out with the swipe)
        if T.PC_CARD_IN <= t < T.SWIPE_END + 0.2:
            if t < T.SWIPE_START - 0.1:
                lt = t - T.PC_CARD_IN
                draw_sprite(img, self.pc_card, W / 2, self.card_pos_y(), spring(lt), alpha=min(1, lt / 0.06))
            else:
                self.swipe_card(img, t)

        # "see how" card between the swipe and the phone card
        if T.SEE_HOW_IN <= t < T.PHONE_CARD_IN:
            lt = t - T.SEE_HOW_IN
            ex = (t - (T.PHONE_CARD_IN - 0.12)) / 0.12
            sc, al = spring(lt), min(1, lt / 0.06)
            if ex > 0:
                sc *= 1 - 0.3 * ease_io(ex)
                al *= 1 - ease_io(ex)
            draw_sprite(img, self.see_card, W / 2, self.card_pos_y(), sc, alpha=al)

        # phone card
        if T.PHONE_CARD_IN <= t < T.END_IN:
            lt = t - T.PHONE_CARD_IN
            draw_sprite(img, self.phone_card, W / 2, self.card_pos_y(), spring(lt), alpha=min(1, lt / 0.06))

        # captions
        for k, (sp, t0, t1, style) in enumerate(self.caps):
            end = self.caps[k + 1][1] if k + 1 < len(self.caps) else T.END_IN
            end = min(end, T.END_IN)
            if t0 <= t < end:
                lt = t - t0
                cx, cy = W / 2, 1590
                if style == "slam":
                    sc = 1 + 0.55 * (1 - spring(lt, 0.6, 28.0))
                    if lt < 0.2:
                        cx += math.sin(lt * 140) * 9 * (1 - lt / 0.2)
                        cy += math.cos(lt * 120) * 6 * (1 - lt / 0.2)
                    self.overlay_flash(img, 0.30 * math.exp(-lt * 14), CYAN)
                else:
                    sc = 0.55 + 0.45 * spring(lt)
                al = min(1, lt / 0.045)
                if end - t < 0.04 and end < T.END_IN:
                    al *= max(0.0, (end - t) / 0.04)
                draw_sprite(img, sp, cx, cy, sc, alpha=al)

        # end card
        if t >= T.END_IN:
            lt = t - T.END_IN
            k = ease_io(lt / 0.25)
            glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse((90, 520, 990, 1400), fill=PURPLE + (int(120 * k),))
            glow = glow.filter(ImageFilter.GaussianBlur(120))
            img.alpha_composite(glow)
            for sp, y, delay in self.cta:
                st = lt - delay
                if st > 0:
                    wob = 1 + 0.012 * math.sin(lt * 6 + y)
                    draw_sprite(img, sp, W / 2, y, spring(st) * wob, alpha=min(1, st / 0.06))
            ut = lt - 0.55
            if ut > 0:
                wdt = int(self.cta[2][0].width * 0.74 * ease_out(ut / 0.3))
                d = ImageDraw.Draw(img)
                d.rounded_rectangle((W / 2 - wdt / 2, 1212, W / 2 + wdt / 2, 1226), 7, fill=YELLOW + (255,))

        return np.asarray(img.convert("RGB"))


def main():
    b = Build()
    if sys.argv[1] == "--preview":
        out = os.path.join(WORK, "preview")
        os.makedirs(out, exist_ok=True)
        for s in sys.argv[2].split(","):
            f = int(s)
            Image.fromarray(b.render(f)).save(os.path.join(out, f"f{f:03d}.png"))
        print("wrote previews", sys.argv[2])
        return
    dest = sys.argv[1]
    audio = os.path.join(WORK, "audio_final.wav")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio,
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           "-t", f"{T.TOTAL_FRAMES / FPS}", dest]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(T.TOTAL_FRAMES):
        p.stdin.write(np.ascontiguousarray(b.render(f)).tobytes())
        if f % 60 == 0:
            print("frame", f, flush=True)
    p.stdin.close()
    p.wait()
    print("done", dest, "rc", p.returncode)


if __name__ == "__main__":
    main()
