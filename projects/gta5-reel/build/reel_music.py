import sys, json, subprocess, re, numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from timeline import *

P = sys.argv[1]
SR = 48000
NS = int(round(TOTAL * SR))
rng = np.random.default_rng(7)
STEP = BEAT / 4            # one 16th = 0.1 s
BAR = 4 * BEAT             # 1.6 s

def tt(d): return np.arange(int(d * SR)) / SR
def sos(kind, fc, order=2): return butter(order, fc, kind, fs=SR, output="sos")
def lp(x, fc): return sosfilt(sos("low", fc), x)
def hp(x, fc): return sosfilt(sos("high", fc), x)
def bp(x, lo, hi): return sosfilt(sos("band", [lo, hi]), x)
def noise(d): return rng.standard_normal(int(d * SR))
def saw(f, t): return 2 * ((f * t) % 1) - 1

def place(buf, x, t, g=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= NS or i < 0: return
    if x.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4) * 1.4142, np.sin((pan + 1) * np.pi / 4) * 1.4142
        x = np.stack([x * l, x * r])
    n = min(x.shape[1], NS - i)
    buf[:, i:i + n] += g * x[:, :n]

# ---- reverb (synthetic stereo IR)
_irs = []
for _ in range(2):
    d = 1.2; t = tt(d); ir = lp(noise(d), 6000) * np.exp(-t / 0.3); ir[:int(0.012 * SR)] = 0
    _irs.append(ir / np.sqrt(np.sum(ir ** 2)))
def rev(x, wet=0.3):
    if x.ndim == 1: x = np.stack([x, x])
    wl = fftconvolve(x[0], _irs[0])[:x.shape[1] + 3000]; wr = fftconvolve(x[1], _irs[1])[:x.shape[1] + 3000]
    out = np.zeros((2, x.shape[1] + 3000)); out[:, :x.shape[1]] += x * (1 - wet * 0.5)
    out[0] += wl * wet; out[1] += wr * wet
    return out

# ---- drums
def kick(v=1.0):
    t = tt(0.4); f = 46 + 125 * np.exp(-t / 0.026); ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-t / 0.115) + lp(noise(0.4), 3500) * np.exp(-t / 0.004) * 0.25) * v
def clap(v=1.0):
    t = tt(0.3); n = bp(noise(0.3), 900, 6500); e = np.exp(-t / 0.085) * 0.45 * (t > 0.03)
    for d in (0, 0.011, 0.022): e += np.where(t >= d, np.exp(-(t - d) / 0.008), 0) * 0.6
    return n * e * v
def hat(v=1.0, open_=False):
    d = 0.22 if open_ else 0.06; t = tt(d)
    return hp(noise(d), 7500) * np.exp(-t / (0.07 if open_ else 0.017)) * v * 0.5
def snare(v=1.0):
    t = tt(0.25); return (bp(noise(0.25), 1500, 7000) * np.exp(-t / 0.07) * 0.7 + np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05) * 0.4) * v

# ---- tonal
def pad_note(f, d, cut):
    t = tt(d); s = sum(saw(f * (1 + k), t) for k in (-0.006, 0, 0.006)) / 3
    a = np.minimum(t / 0.3, 1) * np.clip((d - t) / 0.2, 0, 1)
    return lp(s, cut) * a
def pluck(f, d=0.24, cut=5000):
    t = tt(d); s = saw(f, t); env = np.exp(-t / 0.08)
    return (lp(s, cut) * env + lp(s, 800) * (1 - env)) * np.minimum(t / 0.003, 1) * np.exp(-t / 0.15)
def bass_note(f, d=0.2):
    t = tt(d); s = lp(saw(f, t), 420) + 0.9 * np.sin(2 * np.pi * f * t)
    return s * np.minimum(t / 0.004, 1) * np.exp(-t / 0.16) * np.clip((d - t) / 0.02, 0, 1)

CHORDS = {  # root(bass), triad
    "Am": (110.00, [220.00, 261.63, 329.63]), "F": (87.31, [174.61, 220.00, 261.63]),
    "C": (130.81, [261.63, 329.63, 392.00]), "G": (98.00, [196.00, 246.94, 293.66]),
}
PROG = ["Am", "F", "C", "G", "Am", "F", "C", "G", "Am"]

music = np.zeros((2, NS)); kick_times = []
mute_lo, mute_hi = 6.22, 6.40          # near-silence before the drop
STOP = 14.04                           # music ends on the final stab

for b, name in enumerate(PROG):
    bs = b * BAR; root, tri = CHORDS[name]
    full = b in (2, 3, 4, 5, 6, 8)      # bass + clap bars
    drop = b in (4, 5, 6)
    brk = b == 7
    # pad (filter opens through the intro)
    cut = {0: 650, 1: 1500}.get(b, 2400)
    pad = sum(pad_note(f, BAR + 0.1, cut) for f in tri)
    place(music, rev(pad / 3, 0.25), bs, 0.40 if not brk else 0.55)
    # kick
    kb = [0, 1, 2, 3]
    if brk: kb = [0, 2]
    for k in kb:
        tk = bs + k * BEAT; kick_times.append(tk); place(music, kick(0.80 if b < 2 else 1.0), tk, 0.95)
    # clap on 2 & 4
    if full or b == 7:
        for k in (1, 3):
            if brk and k == 1: continue
            place(music, clap(), bs + k * BEAT, 0.50)
    # hats
    for s in range(16):
        ts = bs + s * STEP
        if b == 0: continue
        if b in (1, 7) and s % 2 == 0: continue
        if b in (1, 7) and s % 4 != 3 and s % 4 != 1: pass
        if b in (1, 7):
            place(music, hat(0.8), ts, 0.30)
        elif s % 2 == 1 or b in (3, 4, 5, 6, 8):
            if s % 4 == 2: place(music, hat(1.0, open_=True), ts, 0.28)
            else: place(music, hat(0.6 + 0.3 * (s % 2)), ts, 0.28)
    # bass: 8th pulse
    if full:
        for e, on in enumerate([1, 0, 1, 1, 0, 1, 1, 0]):
            if on:
                f = root * (2 if e in (3, 6) and drop else 1)
                place(music, bass_note(f), bs + e * 2 * STEP, 0.85)
    # arp (ping-pong)
    if b >= 1:
        pat = [0, 1, 2, 3, 2, 1, 2, 1]
        notes = tri + [tri[0] * 2]
        for s in range(16):
            f = notes[pat[s % 8]] * (2 if brk or drop else 1)
            g = (0.30 if b == 1 else 0.42) if not drop else 0.50
            p = -0.5 if s % 2 == 0 else 0.5
            ts = bs + s * STEP
            n = pluck(f, cut=6500 if drop else 4500)
            place(music, n, ts, g, p)
            place(music, n, ts + 0.3, g * 0.30, -p)
            place(music, n, ts + 0.6, g * 0.10, p)
    # lead hook on the drop
    if b in (5, 6, 8):
        lead_idx = [2, 3, 2, 1, 3, 2, 1, 0]
        for e in range(8):
            f = tri[lead_idx[e] % 3] * 2 * (2 if lead_idx[e] == 3 else 1)
            t = tt(0.22); s = lp(saw(f, t), 3500) * np.exp(-t / 0.12) * np.minimum(t / 0.004, 1)
            place(music, rev(s, 0.3), bs + e * 2 * STEP, 0.30)

# build snare roll (5.6 -> 6.2) rising
for k in range(int((6.2 - 5.6) / STEP)):
    ts = 5.6 + k * STEP; v = 0.35 + 0.65 * k / 6
    place(music, snare(v), ts, 0.45)
# final stab at 14.0
for f in (220.0, 261.63, 329.63, 440.0, 110.0):
    t = tt(0.5); s = lp(saw(f, t), 3200) * np.exp(-t / 0.22) * np.minimum(t / 0.003, 1)
    place(music, rev(s, 0.35), 14.0, 0.35)
place(music, kick(1.0), 14.0, 1.0)

# sidechain pump from kicks
pump = np.ones(NS)
for tk in kick_times:
    i = int(tk * SR); seg = np.arange(min(NS - i, int(0.3 * SR))) / SR
    pump[i:i + len(seg)] *= 1 - 0.50 * np.exp(-seg / 0.09)
music *= pump
# near-silence before the drop and hard stop at the end
tm = np.arange(NS) / SR
gate = np.ones(NS); m = (tm >= mute_lo) & (tm < mute_hi); gate[m] = 0
m2 = tm >= STOP; gate[m2] = np.clip(1 - (tm[m2] - STOP) / 0.03, 0, 1)
music *= gate

# ---- sound effects
def sweep(n, f0, f1, u):
    fcs = np.geomspace(150, 9000, 14); fct = f0 * (f1 / f0) ** u
    out = np.zeros(len(n)); wsum = np.zeros(len(n))
    for fc in fcs:
        w = np.exp(-0.5 * ((np.log(fct) - np.log(fc)) / 0.4) ** 2)
        out += bp(n, fc / 1.5, min(fc * 1.5, 20000)) * w; wsum += w
    return out / np.clip(wsum, 0.5, None)
def whoosh(d, f0, f1, shape="bell"):
    t = tt(d); u = t / d; n = noise(d)
    env = np.sin(np.pi * u) ** 1.6 if shape == "bell" else (u ** 2) * np.clip((1 - u) * 6, 0, 1)
    return sweep(n, f0, f1, u) * env * 1.4
def impact(v=1.0, tail=1.1, wet=0.35):
    t = tt(tail); f = 38 + 95 * np.exp(-t / 0.12); ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sin(ph) * np.exp(-t / 0.4) * 0.9 + lp(noise(tail), 5000) * np.exp(-t / 0.05) * 0.7
         + hp(noise(tail), 2000) * np.exp(-t / 0.12) * 0.25) * v
    return rev(x, wet)
def pop(f0=520, f1=780, d=0.09):
    t = tt(d); f = f0 + (f1 - f0) * np.minimum(t / 0.03, 1)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.02)) * np.minimum(t / 0.001, 1)
def thud():
    t = tt(0.25); f = 60 + 90 * np.exp(-t / 0.03); return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.08)
def riser(d):
    t = tt(d); u = t / d
    n = sweep(noise(d), 300, 7500, u) * 1.3
    tone = np.sin(2 * np.pi * np.cumsum(200 * 8 ** u) / SR) * 0.35
    return (n + tone) * (u ** 2.2)
def ding():
    t = tt(1.6); x = sum(a * np.sin(2 * np.pi * 1318.5 * r * t) * np.exp(-t / tau)
                        for r, a, tau in ((1, 1, 0.7), (2.76, 0.35, 0.4), (5.4, 0.12, 0.2)))
    return rev(x * np.minimum(t / 0.002, 1), 0.3)

sfx = np.zeros((2, NS))
ev = [
    (0.08, impact(0.9), 0.80, 0), (0.12, pop(440, 660), 0.45, 0), (0.22, whoosh(0.35, 400, 6000), 0.30, 0),
    (2.30, whoosh(0.25, 5000, 500), 0.28, 0),
    (2.98, whoosh(0.30, 500, 6500), 0.38, 0), (3.04, pop(520, 780), 0.50, -0.2),
    (3.20, thud(), 0.55, 0),
    (5.28, pop(700, 1000), 0.42, 0.2),
    (4.80, riser(1.42), 0.50, 0),
    (SWIPE[0] - 0.02, whoosh(0.30, 700, 7000), 0.75, 0.3),
    (5.84, impact(1.0, wet=0.5), 0.85, 0), (5.84, pop(800, 1100), 0.45, 0),
    (6.40, impact(0.9, wet=0.3), 0.75, 0),
    (6.95, pop(640, 900), 0.45, -0.2), (8.22, pop(700, 980), 0.45, 0.2),
    (9.18, whoosh(0.30, 500, 6500), 0.38, 0), (9.22, pop(520, 780), 0.50, 0.2), (9.25, pop(640, 920), 0.40, -0.2),
    (10.01, pop(700, 1000), 0.42, 0.2), (10.79, pop(800, 1100), 0.45, 0), (10.79, impact(0.6, wet=0.3), 0.55, 0),
    (11.20, impact(1.0, wet=0.45), 0.9, 0), (11.20, whoosh(0.45, 6000, 400), 0.35, 0),
    (11.30, pop(480, 720), 0.50, -0.2), (11.42, pop(560, 840), 0.50, 0.2), (11.54, pop(640, 960), 0.50, 0),
    (11.95, ding(), 0.30, 0),
    (14.00, impact(1.0, tail=0.5, wet=0.6), 0.9, 0),
]
for t0, x, g, pan in ev: place(sfx, x, t0, g, pan)
# riser is cut at the near-silence
sfx[:, (tm >= mute_lo) & (tm < 6.28)] *= 0
# end: short fade-out so nothing clicks
fo = tm >= TOTAL - 0.12
music[:, fo] *= np.clip((TOTAL - tm[fo]) / 0.12, 0, 1); sfx[:, fo] *= np.clip((TOTAL - tm[fo]) / 0.12, 0, 1)

# ---- voice-driven ducking
sr, v = wavfile.read(f"{P}/work/voice_proc.wav"); v = v.astype(np.float64)
if len(v) < NS: v = np.pad(v, (0, NS - len(v)))
v = v[:NS]
hop = int(0.02 * SR); nb = NS // hop
rms = np.array([np.sqrt(np.mean(v[i * hop:(i + 1) * hop] ** 2)) for i in range(nb)])
db = 20 * np.log10(rms + 1e-9); act = np.clip((db + 32) / 6, 0, 1)
env = np.zeros(nb); a_att, a_rel = 1 - np.exp(-0.02 / 0.015), 1 - np.exp(-0.02 / 0.22)
for i in range(1, nb):
    c = a_att if act[i] > env[i - 1] else a_rel
    env[i] = env[i - 1] + c * (act[i] - env[i - 1])
envf = np.interp(np.arange(NS) / SR, (np.arange(nb) + 0.5) * hop / SR, env)
MUSIC_G, SFX_G = 0.34, 0.48       # gain staging: voice stays the loudest thing
music_d = music * MUSIC_G * (1 - 0.68 * envf); sfx_d = sfx * SFX_G * (1 - 0.40 * envf)

voice = np.stack([v, v])
mix = voice + music_d + sfx_d
def save(name, a): wavfile.write(f"{P}/work/{name}.wav", SR, a.T.astype(np.float32))
save("music", music * MUSIC_G); save("sfx", sfx * SFX_G); save("mix_premaster", mix)
def seg_db(a, lo, hi):
    x = a[:, int(lo*SR):int(hi*SR)]; return 20*np.log10(np.sqrt(np.mean(x**2)) + 1e-9)
for nm, lo, hi in (("speech 5-10s", 5, 10), ("end card 11.4-13.8s", 11.4, 13.8)):
    print("RMS dB %-20s voice %6.1f  music %6.1f  sfx %6.1f" % (nm, seg_db(voice, lo, hi), seg_db(music_d, lo, hi), seg_db(sfx_d, lo, hi)))
print("peaks  voice %.2f  music %.2f  sfx %.2f  mix %.2f" % tuple(np.max(np.abs(a)) for a in (voice, music_d, sfx_d, mix)))

# ---- master: two-pass loudnorm to -14 LUFS / -1.5 dBTP
def ff(args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args, capture_output=True, text=True); return r.stderr
ff(["-y", "-i", f"{P}/work/mix_premaster.wav", "-af", "alimiter=limit=0.80:attack=3:release=50:level=false", "-c:a", "pcm_f32le", f"{P}/work/mix_lim.wav"])
log = ff(["-i", f"{P}/work/mix_lim.wav", "-af", "loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json", "-f", "null", "-"])
m = json.loads(log[log.rfind("{"):])
af = ("loudnorm=I=-14:TP=-1.5:LRA=9:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
      % (m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
ff(["-y", "-i", f"{P}/work/mix_lim.wav", "-af", af + ",aresample=48000", "-c:a", "pcm_s16le", f"{P}/work/master.wav"])
def measure():
    c = ff(["-i", f"{P}/work/master.wav", "-af", "ebur128=peak=true", "-f", "null", "-"]); c = c[c.rfind("Summary"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", c).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", c).group(1)), c
li, tp, _ = measure()
if abs(li + 14) > 0.15 and tp + (-14 - li) < -1.6:
    ff(["-y", "-i", f"{P}/work/master.wav", "-af", "volume=%.2fdB" % (-14 - li), "-c:a", "pcm_s16le", f"{P}/work/master_t.wav"])
    import os; os.replace(f"{P}/work/master_t.wav", f"{P}/work/master.wav")
chk = ff(["-i", f"{P}/work/master.wav", "-af", "ebur128=peak=true", "-f", "null", "-"])
tail = chk[chk.rfind("Summary"):]
print(re.sub(r"\n\s*\n", "\n", tail).strip())
