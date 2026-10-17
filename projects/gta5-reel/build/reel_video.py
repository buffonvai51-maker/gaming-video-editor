"""Render the GTA 5 reel frames (1080x1920, 30 fps) with numpy/OpenCV/PIL.
usage: reel_video.py <project_dir> <out.mp4>          full render (video only)
       reel_video.py <project_dir> --stills t1,t2,..  PNG stills for QA"""
import sys, os, subprocess, numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeline import *
cv2.setNumThreads(4)

P = sys.argv[1]; MODE = sys.argv[2]
FB = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
SS = 1.25                                  # sprites are rendered 1.25x so spring overshoot stays sharp
VW, VH, VY0 = 1080, 1456, 440              # fit-width video band
TAG_Y, BAN_Y, CAP_Y = 190, 335, 1565
rng = np.random.default_rng(3)
def rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def cf(h): return np.array(rgb(h), np.float32) / 255

# ------------------------------------------------------------------ source frames
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f"{P}/{RAW}", "-vf", "fps=30", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     capture_output=True).stdout
SW, SH = 368, 496
FR = np.frombuffer(raw, np.uint8).reshape(-1, SH, SW, 3)
_den = {}
def src_frame(i, blur=0.0):
    i = min(max(i, 0), len(FR) - 1)
    if (i, blur) not in _den:
        f = cv2.fastNlMeansDenoisingColored(FR[i], None, 3, 3, 5, 15)
        if blur: f = cv2.GaussianBlur(f, (0, 0), blur)
        _den[(i, blur)] = f
    return _den[(i, blur)]

# ------------------------------------------------------------------ helpers
def ease_out(u): return 1 - (1 - np.clip(u, 0, 1)) ** 3
def spring(x):
    return 0.0 if x <= 0 else 1 - np.exp(-9 * x) * np.cos(2 * np.pi * 2.0 * x)
def zoom_at(t):
    k = ZOOM_KEYS
    for (t0, z0), (t1, z1) in zip(k, k[1:]):
        if t0 <= t <= t1:
            return z0 + (z1 - z0) * ease_out((t - t0) / max(t1 - t0, 1e-6)) if t1 > t0 else z1
    return k[-1][1]
def shake(t):
    dx = dy = 0.0
    for h in HITS:
        d = t - h
        if 0 <= d < 0.3:
            a = 11 * np.exp(-d / 0.07); dx += a * np.sin(2 * np.pi * 28 * d); dy += a * np.cos(2 * np.pi * 23 * d + 1)
    return dx, dy

# ------------------------------------------------------------------ sprites
def prem(img):
    a = np.asarray(img, np.float32) / 255; a[..., :3] *= a[..., 3:4]; return a
def finish(img, glow=PURPLE, gstr=1.6):
    a = img.split()[3]
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0)); sh.putalpha(a.point(lambda v: int(v * 0.55)))
    sh = sh.filter(ImageFilter.GaussianBlur(10 * SS)); sh2 = Image.new("RGBA", img.size, (0, 0, 0, 0)); sh2.paste(sh, (0, int(8 * SS)))
    gl = Image.new("RGBA", img.size, rgb(glow) + (0,)); gl.putalpha(a.filter(ImageFilter.GaussianBlur(16 * SS)).point(lambda v: min(255, int(v * gstr))))
    return Image.alpha_composite(Image.alpha_composite(sh2, gl), img)
def text_img(parts, size, stroke, scol=PURPLE, max_w=None, tracking=0, pad=48, glow=PURPLE, fin=True):
    size = int(size * SS); stroke = int(stroke * SS); pad = int(pad * SS)
    def meas(sz):
        f = ImageFont.truetype(FB, sz); ws = [f.getlength(t) + tracking * len(t) for t, _ in parts]; sp = f.getlength(" ")
        return f, ws, sp, sum(ws) + sp * (len(parts) - 1)
    f, ws, sp, tot = meas(size)
    if max_w and tot > max_w * SS:
        k = max_w * SS / tot; size = int(size * k); stroke = max(2, int(stroke * k)); f, ws, sp, tot = meas(size)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (int(tot) + 2 * pad + 2 * stroke, asc + desc + 2 * pad + 2 * stroke), (0, 0, 0, 0))
    d = ImageDraw.Draw(img); x = pad + stroke
    for (txt, col), w in zip(parts, ws):
        if tracking:
            cx = x
            for ch in txt:
                d.text((cx, pad + stroke), ch, font=f, fill=rgb(col), stroke_width=stroke, stroke_fill=rgb(scol)); cx += f.getlength(ch) + tracking
        else:
            d.text((x, pad + stroke), txt, font=f, fill=rgb(col), stroke_width=stroke, stroke_fill=rgb(scol))
        x += w + sp
    return finish(img, glow) if fin else img
def stack(imgs, gap=0):
    w = max(i.width for i in imgs); h = sum(i.height for i in imgs) + gap * (len(imgs) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0)); y = 0
    for i in imgs: out.alpha_composite(i, ((w - i.width) // 2, y)); y += i.height + gap
    return out
def bbox_trim(img):
    bb = img.getbbox(); return img.crop(bb) if bb else img

def banner(kind):
    S = SS; pad = int(40 * S); w, h = int((610 if kind == 'pc' else 720) * S), int(190 * S)
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle([pad, pad, pad + w, pad + h], radius=int(40 * S), fill=(16, 2, 44, 240), outline=rgb(CYAN), width=int(5 * S))
    d.rounded_rectangle([pad + 14 * S, pad + 14 * S, pad + w - 14 * S, pad + h - 14 * S], radius=int(30 * S), outline=rgb(PURPLE), width=int(2 * S))
    cy = pad + h / 2; ix = pad + 52 * S
    if kind == "pc":
        d.rounded_rectangle([ix, cy - 50 * S, ix + 116 * S, cy + 24 * S], radius=int(10 * S), fill=(70, 0, 150), outline=rgb(CYAN), width=int(5 * S))
        d.rectangle([ix + 46 * S, cy + 24 * S, ix + 70 * S, cy + 42 * S], fill=rgb(CYAN))
        d.rounded_rectangle([ix + 26 * S, cy + 42 * S, ix + 90 * S, cy + 52 * S], radius=int(5 * S), fill=rgb(CYAN))
        for k in range(5): d.line([ix + 16 * S, cy - 36 * S + k * 11 * S, ix + (60 + 8 * k) * S, cy - 36 * S + k * 11 * S], fill=rgb(YELLOW), width=int(3 * S))
        t = bbox_trim(text_img([("PC", CYAN), ("PLAN", YELLOW)], 84, 9, fin=False))
        img.alpha_composite(t, (int(pad + 205 * S), int(cy - t.height / 2)))
    else:
        d.rounded_rectangle([ix + 14 * S, cy - 62 * S, ix + 82 * S, cy + 62 * S], radius=int(15 * S), fill=(0, 20, 60), outline=rgb(CYAN), width=int(5 * S))
        for k in range(int(100 * S)):
            u = k / (100 * S); c = tuple(int(a + (b - a) * u) for a, b in zip(rgb(CYAN), rgb(PURPLE)))
            d.line([ix + 22 * S, cy - 50 * S + k, ix + 74 * S, cy - 50 * S + k], fill=c, width=1)
        d.ellipse([ix + 41 * S, cy - 58 * S, ix + 55 * S, cy - 52 * S], fill=(0, 20, 60))
        t1 = bbox_trim(text_img([("SMARTPHONE", CYAN)], 62, 7, fin=False)); t2 = bbox_trim(text_img([("= GTA 5", YELLOW)], 52, 6, fin=False))
        st = stack([t1, t2], gap=int(10 * S))
        img.alpha_composite(st, (int(pad + 150 * S), int(cy - st.height / 2)))
    return prem(finish(img, CYAN, 0.9))

def pill(txt, size, track, padx=34, pady=14):
    f = ImageFont.truetype(FB, int(size * SS)); wt = sum(f.getlength(c) + track * SS for c in txt)
    pad = int(40 * SS); w = int(wt + 2 * padx * SS); h = int((size * 1.35 + 2 * pady) * SS)
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle([pad, pad, pad + w, pad + h], radius=h // 2, fill=(16, 2, 44, 225), outline=rgb(CYAN), width=int(3 * SS))
    asc, desc = f.getmetrics(); x = pad + padx * SS; y = pad + (h - asc - desc) / 2
    for c in txt: d.text((x, y), c, font=f, fill=(255, 255, 255)); x += f.getlength(c) + track * SS
    return prem(finish(img, CYAN, 0.9))

def compose_title():
    l1 = bbox_trim(text_img([("GTA 5 ON YOUR PHONE", YELLOW)], 74, 9, max_w=930, fin=False))
    l2 = bbox_trim(text_img([("NO PC!", CYAN)], 150, 15, fin=False))
    st = stack([l1, l2], gap=int(4 * SS)); pad = int(50 * SS)
    img = Image.new("RGBA", (st.width + 2 * pad, st.height + 2 * pad), (0, 0, 0, 0)); img.alpha_composite(st, (pad, pad))
    return prem(finish(img))
TITLE_SP = compose_title()
TAG_SP = pill("THE XAAD UNIVERSE", 28, 4)
TAG_BIG = pill("THE XAAD UNIVERSE", 38, 6, padx=40, pady=16)
PC_SP, PHONE_SP = banner("pc"), banner("phone")
CAP_SP = []
for parts, a, b, fl in CAPTIONS:
    big = fl.get("big"); CAP_SP.append(prem(text_img(parts, 118 if big else 98, 13 if big else 11, max_w=930)))
UNDER = prem(finish(Image.fromarray(np.dstack([np.full((22, 640, 3), rgb(YELLOW), np.uint8), np.full((22, 640), 255, np.uint8)])).convert("RGBA")
                    .resize((int(640 * SS), int(22 * SS))), YELLOW, 1.2))
CTA1 = prem(text_img([("FOLLOW", CYAN)], 170, 15, max_w=900))
CTA2 = prem(text_img([("FOR MORE", "#FFFFFF")], 80, 9, max_w=900))
CTA3 = prem(text_img([("GAMING TIPS!", YELLOW)], 120, 12, max_w=950))
dot = np.zeros((28, 28, 4), np.float32); yy, xx = np.mgrid[:28, :28]; g = np.exp(-(((xx - 13.5) ** 2 + (yy - 13.5) ** 2) / 22)).astype(np.float32)
DOT = {c: np.dstack([g * v for v in (*cf(c), 1)]).astype(np.float32) * np.array([1, 1, 1, 1], np.float32) for c in (CYAN, YELLOW)}
for c in DOT: DOT[c][..., :3] *= DOT[c][..., 3:4] / np.maximum(DOT[c][..., 3:4], 1e-6) * DOT[c][..., 3:4] if False else 1
PARTS = [(rng.uniform(80, 1000), rng.uniform(0, 1), rng.uniform(40, 120), rng.uniform(0, 6), rng.choice([CYAN, YELLOW])) for _ in range(26)]

# ------------------------------------------------------------------ background + masks
yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
stops = [(0.0, (0.10, 0.0, 0.26)), (0.22, (0.25, 0.02, 0.56)), (0.55, (0.10, 0.0, 0.25)), (1.0, (0.02, 0.0, 0.07))]
BASE = np.stack([np.interp(yy[:, 0], [s[0] for s in stops], [s[1][c] for s in stops]) for c in range(3)], -1).astype(np.float32)[:, None, :]
BASE = np.broadcast_to(BASE, (H, W, 3)).copy()
SY, SX = np.mgrid[:240, :135]
def glow(cx, cy, r): return np.exp(-(((SX * 8 - cx) ** 2 + (SY * 8 - cy) ** 2) / (2 * r * r))).astype(np.float32)[..., None]
DIAG = (np.add.outer(np.arange(600), np.arange(W)) % 150).astype(np.int32)
def background(t):
    g = (glow(900 + 60 * np.sin(t * 0.8), 160 + 40 * np.cos(t * 0.6), 330) * cf(CYAN) * 0.42
         + glow(120 + 50 * np.cos(t * 0.7), 560 + 60 * np.sin(t * 0.5), 380) * cf(PURPLE) * 0.60
         + glow(540, 1500 + 40 * np.sin(t), 520) * cf(PURPLE) * 0.20)
    bg = BASE + cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)
    off = int(t * 55) % 150
    line = np.clip(1 - np.abs(((DIAG[:560] + off) % 150) - 4) / 3.0, 0, 1)[..., None] * cf(CYAN) * 0.07
    bg[:560] += line
    return bg
yv, xv = np.mgrid[:H, :W]
VIG = (1 - 0.26 * (((xv - W / 2) / (W / 2)) ** 2 * 0.5 + ((yv - H / 2) / (H / 2)) ** 2 * 0.6)).astype(np.float32)[..., None]
u = np.clip(np.arange(VH) / 120.0, 0, 1); v = np.clip((VH - np.arange(VH)) / 50.0, 0, 1)
MASK = ((u * u * (3 - 2 * u)) * (v * v * (3 - 2 * v))).astype(np.float32)[:, None, None]
GRAIN = [(rng.standard_normal((VH, VW, 1)) * 0.011).astype(np.float32) for _ in range(6)]

def video_band(t, end=False):
    z = zoom_at(t); sx, sy = shake(t)
    i = int(round(out_to_src(t) * FPS))
    if end:                                           # blurred cover backdrop
        f = src_frame(i, blur=5.0); s = (H / SH) * z
        M = np.float32([[s, 0, W / 2 - SW / 2 * s + sx], [0, s, H / 2 - SH / 2 * s + sy]])
        img = cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255
        return img * 0.42 + cf(PURPLE) * 0.10
    f = src_frame(i); cw, ch = SW / z, SH / z; ax, ay = 0.5, 0.38
    x0, y0 = ax * (SW - cw), ay * (SH - ch); a, d = VW / cw, VH / ch
    M = np.float32([[a, 0, -x0 * a + sx], [0, d, -y0 * d + sy]])
    img = cv2.warpAffine(f, M, (VW, VH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255
    luma = (img @ np.float32([0.299, 0.587, 0.114]))[..., None]
    img = (img - 0.5) * 1.07 + 0.5; img = luma + (img - luma) * 1.12
    img += (1 - luma) * np.float32([0.012, 0.004, 0.030])
    img += 0.45 * (img - cv2.GaussianBlur(img, (0, 0), 1.6))
    return img + GRAIN[int(t * FPS) % 6]

# ------------------------------------------------------------------ compositor
LAYER = np.zeros((H, W, 4), np.float32); TMP = np.zeros((H, W, 4), np.float32)
def blit(layer, spr, cx, cy, sc=1.0, a=1.0, rot=0.0, mode="over", wgt=1.0):
    if a <= 0.001 or sc <= 0.01: return
    h, w = spr.shape[:2]; M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, sc / SS); M[0, 2] += cx - w / 2; M[1, 2] += cy - h / 2
    pts = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], np.float32) @ M.T
    x0, x1 = int(max(0, np.floor(pts[:, 0].min()) - 2)), int(min(W, np.ceil(pts[:, 0].max()) + 2))
    y0, y1 = int(max(0, np.floor(pts[:, 1].min()) - 2)), int(min(H, np.ceil(pts[:, 1].max()) + 2))
    if x1 <= x0 or y1 <= y0: return
    M[0, 2] -= x0; M[1, 2] -= y0
    wr = cv2.warpAffine(spr, M, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderValue=0)
    if mode == "over": layer[y0:y1, x0:x1] = wr * a + layer[y0:y1, x0:x1] * (1 - wr[..., 3:4] * a)
    else: layer[y0:y1, x0:x1] += wr * (a * wgt)
def pop_in(t, t0, d=0.0): x = t - t0; return spring(x), float(np.clip(x / 0.07, 0, 1))
def swipe_x(t):
    p = np.clip((t - SWIPE[0]) / (SWIPE[1] - SWIPE[0]), 0, 1); return 1350 * p ** 2.2

def render(t):
    end = t >= END_CARD[0]
    cv = background(t)
    if end:
        cv = cv * 0.40 + video_band(t, True) * 0.9
    else:
        band = video_band(t)
        cv[VY0:VY0 + VH] = band * MASK + cv[VY0:VY0 + VH] * (1 - MASK)
    cv *= VIG
    for hc in (6.40, 9.20, 11.20, 14.00):                 # cut / hit flashes
        d = t - hc
        if 0 <= d < 0.2: cv += np.float32([0.75, 0.92, 1.0]) * 0.40 * np.exp(-d / 0.045)
    L = LAYER; L[:] = 0
    if not end:
        # hook title
        if TITLE[0] <= t < TITLE[1]:
            s, a = pop_in(t, TITLE[0]); ex = np.clip((t - (TITLE[1] - 0.2)) / 0.2, 0, 1)
            blit(L, TITLE_SP, 540, 340 + 4 * np.sin(t * 5), s * (1 - 0.2 * ex), a * (1 - ex))
        if t >= BRAND_TAG_IN:
            s, a = pop_in(t, BRAND_TAG_IN); blit(L, TAG_SP, 540, TAG_Y, s, a)
        # swipe-off group (blurred): PC banner + "MATHA THEKE"
        if PC_BANNER_IN <= t < SWIPE[1] + 0.1:
            items = [(PC_SP, 540, BAN_Y, PC_BANNER_IN)]
            for k, (parts, a0, b0, fl) in enumerate(CAPTIONS):
                if fl.get("swipe") and a0 <= t: items.append((CAP_SP[k], 540, CAP_Y, a0))
            moving = t > SWIPE[0] - 1e-6
            for spr, cx, cy, t0 in items:
                if not moving:
                    s, a = pop_in(t, t0); blit(L, spr, cx, cy + 3 * np.sin(t * 4), s, a)
                else:
                    TMP[:] = 0
                    for kk in range(12):
                        ts = t - (kk / 11) / FPS; s, a = pop_in(min(ts, SWIPE[0]), t0)
                        blit(TMP, spr, cx + swipe_x(ts), cy, s, 1.0, rot=-5 * np.clip((ts - SWIPE[0]) / 0.17, 0, 1), mode="add", wgt=1 / 12)
                    L[:] = TMP + L * (1 - TMP[..., 3:4])
        # normal captions
        for k, (parts, a0, b0, fl) in enumerate(CAPTIONS):
            if fl.get("swipe") or not (a0 <= t < b0): continue
            s, a = pop_in(t, a0); fo = np.clip((t - (b0 - 0.05)) / 0.05, 0, 1)
            rot = -4 * (1 - min(s, 1)) if fl.get("big") else 0
            if fl.get("underline"):
                p = ease_out((t - a0 - 0.05) / 0.25); wcur = int(UNDER.shape[1] * p)
                if wcur > 4:
                    left = 540 - UNDER.shape[1] / SS / 2; blit(L, UNDER[:, :wcur], left + wcur / SS / 2, CAP_Y + 78, 1.0, a * (1 - fo))
            blit(L, CAP_SP[k], 540, CAP_Y, s, a * (1 - fo), rot)
        if PHONE_BANNER[0] <= t < PHONE_BANNER[1]:
            s, a = pop_in(t, PHONE_BANNER[0]); blit(L, PHONE_SP, 540, BAN_Y, s, a)
    else:
        for k, (spr, y, t0) in enumerate(((CTA1, 760, 11.30), (CTA2, 912, 11.42), (CTA3, 1075, 11.54))):
            s, a = pop_in(t, t0)
            if k == 2:
                s *= 1 + 0.02 * np.sin(max(t - 12.2, 0) * 6)
                d = t - 14.0
                if 0 <= d < 0.4: s *= 1 + 0.07 * np.exp(-d / 0.1) * np.cos(d * 30)
            blit(L, spr, 540, y, s, a)
        s, a = pop_in(t, 11.85); blit(L, TAG_BIG, 540, 1290, s, a)
        for px, ph, sp_, off, col in PARTS:                # drifting sparkles
            tt_ = t - 11.3
            if tt_ < 0: continue
            y = 1750 - ((tt_ * sp_ + off * 90) % 1500); a = 0.35 + 0.65 * abs(np.sin(tt_ * 3 + ph * 6))
            blit(L, DOT[col], px + 30 * np.sin(tt_ + ph * 6), y, 1.0 + ph, a * min(tt_ / 0.4, 1))
    out = L[..., :3] + cv * (1 - L[..., 3:4])
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)

if MODE == "--stills":
    os.makedirs(f"{P}/work/stills", exist_ok=True)
    for ts in sys.argv[3].split(","):
        t = float(ts); Image.fromarray(render(t)).save(f"{P}/work/stills/t_{t:06.3f}.png")
    print("stills done")
else:
    n = int(round(TOTAL * FPS))
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                            "-profile:v", "high", "-level", "4.2", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-r", str(FPS), "-an", MODE], stdin=subprocess.PIPE)
    for i in range(n):
        enc.stdin.write(render(i / FPS).tobytes())
        if i % 60 == 0: print("frame", i, "/", n, flush=True)
    enc.stdin.close(); enc.wait(); print("rendered", MODE)
