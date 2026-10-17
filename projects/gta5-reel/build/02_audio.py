#!/usr/bin/env python3
"""Step 2: synthesize music + sound design, duck under voice, mix, loudness-master.

Everything is generated from scratch (numpy/scipy), so there is nothing to license.
Beat grid is locked to the picture: hook hit on beat 0, swipe drop on beat 11,
end card on beat 21.

Output: ../work/audio_final.wav (48k stereo, -14 LUFS integrated, true peak <= -1.5 dB)
"""
import json
import os
import re
import subprocess
import sys
import wave

import numpy as np
from scipy.signal import butter, sosfilt

sys.path.insert(0, os.path.dirname(__file__))
import timeline as T

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORK = os.path.join(ROOT, "work")
SR = 48000
DUR = T.TOTAL_FRAMES / T.FPS
N = int(DUR * SR)
rng = np.random.default_rng(7)


# ---------- helpers ----------
def tt(d):
    return np.arange(int(d * SR)) / SR


def lp(x, fc, order=2):
    return sosfilt(butter(order, fc, "low", fs=SR, output="sos"), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def saw(f, t):
    return 2.0 * ((f * t) % 1.0) - 1.0


def place(buf, sig, t0, gain=1.0, pan=0.0):
    i0 = int(round(t0 * SR))
    if i0 >= buf.shape[1] or i0 + len(sig) <= 0:
        return
    s0 = max(0, -i0)
    i0 = max(0, i0)
    seg = sig[s0:s0 + buf.shape[1] - i0]
    ang = (pan + 1) * np.pi / 4
    buf[0, i0:i0 + len(seg)] += seg * gain * np.cos(ang)
    buf[1, i0:i0 + len(seg)] += seg * gain * np.sin(ang)


def varlp(x, fc_curve):
    """One-pole low-pass with a per-sample cutoff curve (for whoosh/riser sweeps)."""
    a = 1.0 - np.exp(-2 * np.pi * fc_curve / SR)
    y = np.empty_like(x)
    prev = 0.0
    for i in range(len(x)):
        prev += a[i] * (x[i] - prev)
        y[i] = prev
    return y


# ---------- instruments ----------
def kick():
    t = tt(0.4)
    f = 46 + 150 * np.exp(-t * 38)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t * 8.5)
    click = rng.standard_normal(len(t)) * np.exp(-t * 900) * 0.25
    return np.tanh((y + click) * 1.6) * 0.9


def clap():
    t = tt(0.28)
    n = bp(rng.standard_normal(len(t)), 900, 4200)
    e = np.zeros_like(t)
    for off in (0.0, 0.011, 0.022):
        m = t >= off
        e[m] += np.exp(-(t[m] - off) * 110)
    m = t >= 0.034
    e[m] += 0.8 * np.exp(-(t[m] - 0.034) * 17)
    return n * e * 0.55


def hat(open_=False):
    t = tt(0.16 if open_ else 0.07)
    n = hp(rng.standard_normal(len(t)), 7500)
    return n * np.exp(-t * (22 if open_ else 70)) * 0.35


def bass(f, dur):
    t = tt(dur + 0.05)
    y = lp(saw(f, t) * 0.7 + np.sin(2 * np.pi * f * t), 260)
    env = np.minimum(1, t / 0.004) * np.exp(-t * 3.0)
    env *= np.minimum(1, np.maximum(0, (dur + 0.05 - t) / 0.03))
    return np.tanh(y * env * 1.4) * 0.8


def pluck(f, dur=0.36):
    t = tt(dur)
    y = saw(f, t) * 0.6 + np.sign(np.sin(2 * np.pi * f * 1.005 * t)) * 0.3
    y = lp(y, 3600)
    return y * np.exp(-t * 9.5) * np.minimum(1, t / 0.002)


def pad(freqs, dur):
    t = tt(dur + 0.35)
    y = np.zeros_like(t)
    for f in freqs:
        for det in (0.994, 1.0, 1.006):
            y += saw(f * det, t)
    y = lp(y, 1300) / (len(freqs) * 3)
    env = np.minimum(1, t / 0.4) * np.minimum(1, np.maximum(0, (dur + 0.35 - t) / 0.35))
    return y * env


# ---------- sound design ----------
def whoosh(dur, up=True, bright=9000):
    t = tt(dur)
    n = rng.standard_normal(len(t))
    k = t / dur
    fc = (300 + (bright - 300) * k ** 1.6) if up else (bright - (bright - 300) * k ** 0.8)
    y = varlp(n, fc)
    y = y - lp(y, 180)
    env = np.sin(np.pi * np.clip(k, 0, 1) ** (0.7 if up else 1.4)) ** 1.5
    return y * env * 1.6


def impact(depth=1.0):
    t = tt(0.9)
    f = 34 + 120 * np.exp(-t * 14)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sub = np.sin(ph) * np.exp(-t * 4.2)
    noise = lp(rng.standard_normal(len(t)), 5000) * np.exp(-t * 16) * 0.5
    tail = lp(rng.standard_normal(len(t)), 600) * np.exp(-t * 5) * 0.25
    return np.tanh((sub * 1.2 + noise + tail) * 1.3) * 0.9 * depth


def pop(pitch=880):
    t = tt(0.09)
    f = pitch * (1 + 0.45 * np.minimum(1, t / 0.03))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 55)
    tick = hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 400) * 0.2
    return (y + tick) * 0.6


def riser(dur):
    t = tt(dur)
    k = t / dur
    n = varlp(rng.standard_normal(len(t)), 250 + 9000 * k ** 2.2)
    tone = np.sin(2 * np.pi * np.cumsum(180 + 900 * k ** 1.7) / SR) * 0.35
    env = (0.12 + 0.88 * k ** 1.8) * np.minimum(1, (dur - t) / 0.01)
    return (n * 1.4 + tone) * env


def ding():
    t = tt(1.1)
    y = (np.sin(2 * np.pi * 1568 * t) * np.exp(-t * 5)
         + 0.6 * np.sin(2 * np.pi * 2349 * t) * np.exp(-t * 7)
         + 0.4 * np.sin(2 * np.pi * 3136 * t) * np.exp(-t * 10))
    return y * 0.4


# ---------- music ----------
CHORDS = [  # root(bass), pad notes, arp notes
    (55.00, [110.0, 261.63, 329.63], [440.00, 523.25, 659.25]),    # Am
    (43.65, [87.31, 220.00, 261.63], [349.23, 440.00, 523.25]),    # F
    (65.41, [130.81, 329.63, 392.00], [392.00, 523.25, 659.25]),   # C
    (49.00, [98.00, 246.94, 293.66], [392.00, 493.88, 587.33]),    # G
]
ARP_PAT = [0, 1, 2, 1, 2, 1, 0, 1]


def build_music():
    buf = np.zeros((2, N))
    B, B0 = T.BEAT, T.BEAT0
    tb = lambda k: B0 + k * B
    kk, cl, h, ho = kick(), clap(), hat(), hat(True)
    last_beat = 27
    LULL = (10, 11)     # beats where groove drops out (snare-roll build)
    for k in range(0, last_beat + 1):
        bar = (k // 4) % 4
        root, padn, arpn = CHORDS[bar]
        in_lull = LULL[0] <= k < LULL[1]
        t0 = tb(k)
        if not in_lull:
            place(buf, kk, t0, 1.0)
        if k >= 4 and not in_lull and k < last_beat:
            place(buf, h, t0 + B / 2, 0.6)
            if k % 4 == 3:
                place(buf, ho, t0 + B / 2, 0.5)
        if k >= 9 and k % 2 == 1 and not in_lull and k < last_beat:
            place(buf, cl, t0, 0.8)
        if not in_lull and k < last_beat:
            amp = 0.55 if k < 4 else 0.8
            place(buf, bass(root, B * 0.45), t0, amp)
            if k >= 4:
                place(buf, bass(root * 2, B * 0.3), t0 + B * 0.75, amp * 0.5)
        if k >= 4 and not in_lull and k < last_beat:
            for j in range(2):
                note = arpn[ARP_PAT[(k * 2 + j) % 8]]
                place(buf, pluck(note), t0 + j * B / 2, 0.30 if k < 11 else 0.38,
                      pan=-0.4 if j == 0 else 0.4)
        if k % 4 == 0 and k >= 11 and k < last_beat:
            place(buf, pad(padn, min(4 * B, tb(last_beat) - t0)), t0, 0.42)
    # snare-roll build into the swipe drop
    for j in range(8):
        t = tt(0.12)
        sn = bp(rng.standard_normal(len(t)), 1500, 6000) * np.exp(-t * 35)
        place(buf, sn, tb(10) + j * B / 8, 0.25 + 0.5 * j / 7)
    # final stab on the last beat
    root, padn, arpn = CHORDS[0]
    place(buf, pad(padn + arpn, 0.2), tb(last_beat), 0.6)
    place(buf, pluck(arpn[0], 0.5), tb(last_beat), 0.5)
    place(buf, kk, tb(last_beat), 1.0)
    place(buf, bass(root, 0.4), tb(last_beat), 0.9)
    # fade out the ring-out
    fade_start = int(tb(last_beat) * SR)
    n = N - fade_start
    buf[:, fade_start:] *= np.linspace(1, 0, n) ** 1.5
    peak = np.abs(buf).max()
    return buf / peak * 0.70


def build_sfx():
    buf = np.zeros((2, N))
    # hook
    place(buf, whoosh(0.16, True), 0.0, 0.8)
    place(buf, impact(1.0), T.BEAT0, 0.9)
    place(buf, whoosh(0.25, False, 7000), T.HOOK_OUT - 0.05, 0.5)
    place(buf, pop(760), T.BRAND_IN, 0.5)
    # PC card in
    place(buf, whoosh(0.15, True, 8000), T.PC_CARD_IN - 0.1, 0.6)
    place(buf, pop(620), T.PC_CARD_IN + 0.05, 0.6)
    # caption pops
    for text, s, e, style in T.CAPTIONS:
        t0 = T.src2out(s)
        if style == "slam":
            place(buf, pop(1100), t0, 0.9)
            place(buf, impact(0.45), t0, 0.5)
        elif style == "hero":
            place(buf, pop(980), t0, 0.7)
        else:
            place(buf, pop(820), t0, 0.5)
    # riser into the swipe, then swipe whoosh + drop impact
    place(buf, riser(T.SWIPE_START - 3.9), 3.9, 0.55)
    place(buf, whoosh(T.SWIPE_END - T.SWIPE_START + 0.05, True, 11000), T.SWIPE_START, 1.0)
    place(buf, impact(1.1), T.SWIPE_END, 1.0)
    # see-how card in
    place(buf, whoosh(0.15, True, 8000), T.SEE_HOW_IN - 0.1, 0.55)
    place(buf, pop(700), T.SEE_HOW_IN + 0.05, 0.55)
    # phone card in
    place(buf, whoosh(0.16, True, 9000), T.PHONE_CARD_IN - 0.1, 0.6)
    place(buf, ding(), T.PHONE_CARD_IN + 0.05, 0.5)
    # end card
    place(buf, impact(1.0), T.END_IN, 0.9)
    place(buf, whoosh(0.35, False, 8000), T.END_IN, 0.6)
    place(buf, ding(), T.END_IN + 0.1, 0.55)
    last = T.BEAT0 + 27 * T.BEAT
    place(buf, riser(last - 12.4), 12.4, 0.5)
    place(buf, impact(1.2), last, 1.0)
    peak = np.abs(buf).max()
    return buf / peak * 0.6


def voice_envelope(v):
    a_att = 1 - np.exp(-1 / (0.008 * SR))
    a_rel = 1 - np.exp(-1 / (0.18 * SR))
    env = np.zeros_like(v)
    prev = 0.0
    x = np.abs(v)
    for i in range(len(x)):
        a = a_att if x[i] > prev else a_rel
        prev += a * (x[i] - prev)
        env[i] = prev
    return env


def write_wav(path, buf):
    data = (np.clip(buf, -1, 1).T * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def read_mono(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
                        "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)


def main():
    voice = read_mono(os.path.join(WORK, "voice.wav"))[:N]
    voice = np.pad(voice, (0, N - len(voice)))
    music, sfx = build_music(), build_sfx()

    env = voice_envelope(voice)
    duck = np.clip(env / 0.12, 0, 1)
    music_g = 1 - 0.60 * duck          # up to about -8 dB under voice
    swell = np.ones(N)
    i_end = int(T.END_IN * SR)
    swell[i_end:] = 1.0 + 0.4 * np.clip(np.arange(N - i_end) / (0.12 * SR), 0, 1)
    music_g = music_g * swell         # music takes over once the voice is done
    sfx_g = 1 - 0.30 * duck            # keep sound design punchy
    mix = np.zeros((2, N))
    mix += voice[None, :] * 1.0
    mix += music * music_g[None, :]
    mix += sfx * sfx_g[None, :]
    write_wav(os.path.join(WORK, "mix_premaster.wav"), mix * 0.9)

    # two-pass loudness normalization
    pre = os.path.join(WORK, "mix_premaster.wav")
    meas = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", pre, "-af",
         "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    j = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", meas, re.S).group(0))
    af = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
          f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:"
          f"offset={j['target_offset']}:linear=true,alimiter=limit=0.84:level=0")
    out = os.path.join(WORK, "audio_final.wav")
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", pre,
                        "-af", af, "-ar", "48000", "-c:a", "pcm_s16le", out],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    print("measured before:", {k: j[k] for k in ("input_i", "input_tp", "input_lra")})
    print("wrote", out)


if __name__ == "__main__":
    main()
