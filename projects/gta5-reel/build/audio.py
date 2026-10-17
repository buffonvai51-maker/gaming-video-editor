"""Audio build: clean voice -> cut to timeline -> synth music + SFX -> duck -> mix -> loudnorm.

Usage: python3 audio.py            (writes ../work/mix_raw.wav and ../work/audio_final.wav)
Everything is synthesized here: no external samples are used.
"""
import os
import subprocess
import sys

import numpy as np
from scipy import signal
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(__file__))
import timeline as T

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "..", "work")
DUR = T.TOTAL_FRAMES / T.FPS
N = int(round(DUR * SR))
rng = np.random.default_rng(7)


def db(x):
    return 10 ** (x / 20)


# ----------------------------------------------------------------------------------
# Voice
# ----------------------------------------------------------------------------------
def denoise(x, sr, noise_a=0.5, noise_b=4.5, alpha=1.6, floor=0.20):
    """Spectral-subtraction gate using the clip's own noise print (room tone before he speaks)."""
    nper, hop = 1024, 256
    f, t, X = signal.stft(x, sr, nperseg=nper, noverlap=nper - hop, window="hann")
    mag, ph = np.abs(X), np.angle(X)
    a, b = int(noise_a * sr / hop), int(noise_b * sr / hop)
    noise_mag = np.sqrt(np.mean(mag[:, a:b] ** 2, axis=1, keepdims=True))
    clean = np.maximum(mag - alpha * noise_mag, floor * mag)
    gain = clean / (mag + 1e-12)
    # smooth over time and frequency to avoid musical noise
    gain = signal.convolve2d(gain, np.ones((3, 5)) / 15, mode="same", boundary="symm")
    _, y = signal.istft(gain * mag * np.exp(1j * ph), sr, nperseg=nper, noverlap=nper - hop, window="hann")
    return y[:len(x)]


def voice_track():
    src = os.path.join(WORK, "src_mono.wav")
    den = os.path.join(WORK, "voice_denoised.wav")
    clean = os.path.join(WORK, "voice_clean.wav")
    sr0, raw = wavfile.read(src)
    raw = raw.astype(np.float64) / 32768.0
    wavfile.write(den, sr0, denoise(raw, sr0).astype(np.float32))
    chain = ",".join([
        "highpass=f=90",
        "equalizer=f=250:t=q:w=1.2:g=-2",         # tame boxiness
        "equalizer=f=3200:t=q:w=1.0:g=3",         # presence / clarity
        "equalizer=f=9000:t=h:w=0.7:g=1.5",       # air
        "deesser=i=0.35:m=0.5:f=0.5",
        "acompressor=threshold=-22dB:ratio=2:attack=8:release=120:makeup=1",
        "alimiter=limit=0.89:attack=2:release=40",
    ])
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", den,
                    "-af", chain, "-ar", str(SR), "-ac", "1", clean], check=True)
    sr, x = wavfile.read(clean)
    x = x.astype(np.float64) / (32768.0 if x.dtype == np.int16 else 1.0)
    out = np.zeros(N)
    fade = int(0.008 * SR)
    for f0, f1, o0 in T.SEGMENTS:
        a, b = int(f0 / T.FPS * SR), int(f1 / T.FPS * SR)
        seg = x[a:b].copy()
        seg[:fade] *= np.linspace(0, 1, fade)
        seg[-fade:] *= np.linspace(1, 0, fade)
        o = int(o0 / T.FPS * SR)
        out[o:o + len(seg)] += seg
    return out


# ----------------------------------------------------------------------------------
# Synth helpers
# ----------------------------------------------------------------------------------
def tvec(n):
    return np.arange(n) / SR


def place(buf, sig, t, gain=1.0, pan=0.0):
    """Add mono sig into stereo buf (2,N) at time t with equal-power pan [-1..1]."""
    i = int(round(t * SR))
    if i >= buf.shape[1]:
        return
    j = min(buf.shape[1], i + len(sig))
    seg = sig[:j - i] * gain
    ang = (pan + 1) * np.pi / 4
    buf[0, i:j] += seg * np.cos(ang)
    buf[1, i:j] += seg * np.sin(ang)


def lp(x, fc, order=2):
    sos = signal.butter(order, fc, "low", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def hp(x, fc, order=2):
    sos = signal.butter(order, fc, "high", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def bp(x, f1, f2):
    sos = signal.butter(2, [f1, f2], "band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def reverb(x, tail=0.9, mix=0.35, seed=1):
    r = np.random.default_rng(seed)
    n = int(tail * SR)
    ir = r.standard_normal(n) * np.exp(-tvec(n) / (tail / 4.5))
    ir = lp(ir, 6000)
    wet = signal.fftconvolve(x, ir)[:len(x) + n // 2]
    wet /= (np.max(np.abs(wet)) + 1e-9) / (np.max(np.abs(x)) + 1e-9)
    out = np.zeros(len(wet))
    out[:len(x)] += x * (1 - mix)
    return out + wet * mix


def kick(dur=0.32):
    t = tvec(int(dur * SR))
    f = 46 + 120 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t / 0.11)
    y += 0.35 * hp(rng.standard_normal(len(t)), 2000) * np.exp(-t / 0.004)
    return y


def clap(dur=0.22):
    n = int(dur * SR)
    t = tvec(n)
    noise = bp(rng.standard_normal(n), 900, 3800)
    env = np.zeros(n)
    for off in (0.0, 0.011, 0.024):
        k = int(off * SR)
        env[k:] += np.exp(-(t[:n - k]) / 0.012)
    env += 0.6 * np.exp(-t / 0.07)
    return noise * env * 0.6


def hat(open_=False):
    dur = 0.2 if open_ else 0.05
    n = int(dur * SR)
    t = tvec(n)
    return hp(rng.standard_normal(n), 7000) * np.exp(-t / (0.07 if open_ else 0.012))


def saw(f, n, detune=0.0):
    t = tvec(n)
    return signal.sawtooth(2 * np.pi * f * (1 + detune) * t)


def bass_note(f, dur):
    n = int(dur * SR)
    t = tvec(n)
    y = np.sin(2 * np.pi * f * t) + 0.5 * lp(saw(f, n), 380)
    env = np.minimum(1, t / 0.006) * np.exp(-t / (dur * 0.8))
    env *= np.minimum(1, (dur - t) / 0.02)
    return y * env


def pluck(f, dur=0.22):
    n = int(dur * SR)
    t = tvec(n)
    y = 0.6 * saw(f, n, 0.003) + 0.6 * saw(f, n, -0.003) + 0.3 * np.sign(np.sin(2 * np.pi * f * t))
    cutoff = 700 + 4200 * np.exp(-t / 0.05)
    # time-varying lowpass via short blocks
    out = np.zeros(n)
    zi = None
    for k in range(0, n, 256):
        sos = signal.butter(2, min(cutoff[k], 12000), "low", fs=SR, output="sos")
        if zi is None:
            zi = signal.sosfilt_zi(sos) * 0
        seg, zi = signal.sosfilt(sos, y[k:k + 256], zi=zi)
        out[k:k + 256] = seg
    return out * np.exp(-t / 0.09) * np.minimum(1, t / 0.003)


def pad_chord(freqs, dur):
    n = int(dur * SR)
    t = tvec(n)
    y = sum(saw(f, n, d) for f in freqs for d in (-0.004, 0.004))
    y = lp(y, 1400)
    env = np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.2).clip(0, 1)
    return y * env / (len(freqs) * 2)


def sweep_noise(dur, f0, f1, q=1.2, shape="up", seed=3):
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    x = r.standard_normal(n)
    fc = np.geomspace(f0, f1, n)
    out = np.zeros(n)
    zi = np.zeros(2)
    blk = 256
    for k in range(0, n, blk):
        w0 = min(fc[k] / (SR / 2), 0.95)
        b, a = signal.iirpeak(w0, q)
        seg, zi = signal.lfilter(b, a, x[k:k + blk], zi=zi)
        out[k:k + blk] = seg
    u = np.linspace(0, 1, n)
    env = {"up": u ** 2.2, "down": (1 - u) ** 1.6, "bell": np.sin(np.pi * u) ** 1.5}[shape]
    out *= env
    return out / (np.max(np.abs(out)) + 1e-9)


def impact(dur=1.4, depth=1.0):
    n = int(dur * SR)
    t = tvec(n)
    f = 38 + 90 * np.exp(-t / 0.05)
    ph = 2 * np.pi * np.cumsum(f) / SR
    boom = np.sin(ph) * np.exp(-t / 0.35)
    crack = lp(rng.standard_normal(n), 5000) * np.exp(-t / 0.05)
    y = depth * boom + 0.5 * crack
    y = reverb(y, tail=1.0, mix=0.3, seed=5)[:n]
    return y / (np.max(np.abs(y)) + 1e-9)


def pop(f0=820, dur=0.09):
    n = int(dur * SR)
    t = tvec(n)
    f = f0 * np.exp(-t / 0.03) + 300
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.03)
    y += 0.25 * hp(rng.standard_normal(n), 3000) * np.exp(-t / 0.004)
    return y


def ding(dur=1.6):
    n = int(dur * SR)
    t = tvec(n)
    y = 0.0
    for f, a, d in ((1318.5, 1.0, 0.9), (2637, 0.45, 0.5), (3951, 0.2, 0.3), (1760, 0.3, 0.6)):
        y = y + a * np.sin(2 * np.pi * f * t + 2.0 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / 0.03)) * np.exp(-t / d)
    y = reverb(y, tail=1.2, mix=0.3, seed=9)[:n]
    return y / (np.max(np.abs(y)) + 1e-9)


# ----------------------------------------------------------------------------------
# Music: 124 BPM, A minor (Am - F - C - G), beat 0 on the hook impact
# ----------------------------------------------------------------------------------
BPM = 124
BEAT = 60 / BPM
T0 = T.HOOK_IN
CHORDS = [(110.0, [220.0, 261.63, 329.63]),      # Am
          (87.31, [174.61, 220.0, 261.63]),      # F
          (130.81, [196.0, 261.63, 329.63]),     # C
          (98.0, [196.0, 246.94, 293.66])]       # G


def midi_arp(chord, step):
    base = [chord[0], chord[1], chord[2], chord[1] * 2, chord[2] * 2, chord[1] * 2, chord[2], chord[1]]
    return base[step % len(base)] * 2


def music():
    buf = np.zeros((2, N + SR))
    end_t = T.END_START_F / T.FPS
    drop0, drop1 = T.MUSIC_DROP
    final_hit = 13.72

    def active(t):
        return not (drop0 <= t < drop1) and t < final_hit - 0.005

    k_s, c_s, ho_s = kick(), clap(), hat(True)
    hc_s = hat(False)
    nbeats = int((final_hit - T0) / BEAT) + 2
    for b in range(nbeats):
        t = T0 + b * BEAT
        bar = (b // 4) % 4
        root, chord = CHORDS[bar]
        in_end = t >= end_t
        if active(t):
            place(buf, k_s, t, 0.95)
        if b % 2 == 1 and active(t) and (t > 2.0 or in_end):
            place(buf, c_s, t, 0.55 if not in_end else 0.8, pan=0.1)
        for sub in (0.5,):
            ts = t + sub * BEAT
            if active(ts):
                place(buf, ho_s if (b % 4 == 3) else hc_s, ts, 0.28, pan=-0.2)
        for s16 in (0.25, 0.75):
            ts = t + s16 * BEAT
            if active(ts) and t > 1.0:
                place(buf, hc_s, ts, 0.11, pan=0.25)
        # bass: 8ths, octave pop on offbeats
        for h, mul in ((0.0, 1.0), (0.5, 2.0)):
            ts = t + h * BEAT
            if active(ts):
                place(buf, bass_note(root * mul, BEAT * 0.45), ts, 0.55 if h == 0 else 0.3)
        # arp: 16ths from beat 4 on, wider/louder on the end card
        if t > 1.9 or in_end:
            for s in range(4):
                ts = t + s * BEAT / 4
                if active(ts):
                    f = midi_arp(chord, b * 4 + s)
                    place(buf, pluck(f), ts, 0.30 if not in_end else 0.42,
                          pan=-0.5 if s % 2 == 0 else 0.5)
    # pads per bar
    nbars = int((final_hit - T0) / (4 * BEAT)) + 1
    for bar in range(nbars):
        t = T0 + bar * 4 * BEAT
        place(buf, pad_chord(CHORDS[bar % 4][1], 4 * BEAT + 0.1), t, 0.34)
    out = buf[:, :N].copy()
    # delay echo on the high end (dotted 8th)
    d = int(BEAT * 0.75 * SR)
    hi = np.stack([hp(out[0], 1500), hp(out[1], 1500)])
    for rep, g in ((1, 0.30), (2, 0.14)):
        out[0, d * rep:] += hi[1, :N - d * rep] * g
        out[1, d * rep:] += hi[0, :N - d * rep] * g
    # intro filter open over the hook, dropout fades, end-card swell
    t = tvec(N)
    g = np.ones(N)
    g *= 0.55 + 0.45 * np.clip(t / 2.0, 0, 1)
    swell = np.clip((t - end_t) / 0.35, 0, 1)
    g *= 1 + 0.45 * swell
    dm = np.ones(N)
    i0, i1 = int(drop0 * SR), int(drop1 * SR)
    dm[i0:i1] = 0
    ramp = int(0.015 * SR)
    dm[i0 - ramp:i0] = np.linspace(1, 0, ramp)
    out *= g * dm
    return out


def duck_curve(voice):
    """Gain curve for music: -12.5 dB while the voice is present."""
    w = int(0.02 * SR)
    rms = np.sqrt(np.convolve(voice ** 2, np.ones(w) / w, "same"))
    present = (rms > db(-44)).astype(float)
    # attack 15 ms, release 280 ms
    out = np.zeros(N)
    cur = 0.0
    a_att = 1 - np.exp(-1 / (0.015 * SR))
    a_rel = 1 - np.exp(-1 / (0.28 * SR))
    for i in range(0, N, 1):
        a = a_att if present[i] > cur else a_rel
        cur += (present[i] - cur) * a
        out[i] = cur
    return 1 - out * (1 - db(-12.5))


# ----------------------------------------------------------------------------------
# SFX
# ----------------------------------------------------------------------------------
def sfx_track():
    buf = np.zeros((2, N + SR))
    imp = impact()
    endimp = impact(1.6, 1.2)
    for name, t in T.SFX:
        if name == "impact":
            place(buf, imp, t, 0.85)
        elif name == "whoosh_in":
            place(buf, sweep_noise(0.42, 300, 5000, 1.0, "up", 11), t, 0.40)
        elif name == "pop":
            place(buf, pop(), t, 0.40)
        elif name == "tick":
            place(buf, pop(1500, 0.05), t, 0.30)
        elif name == "card_in":
            place(buf, sweep_noise(0.30, 500, 3500, 1.2, "bell", 13), t - 0.04, 0.38)
            place(buf, pop(560, 0.12), t + 0.07, 0.38)
        elif name == "riser":
            dur = T.FLICK[0] - t
            r = sweep_noise(dur, 250, 6500, 2.0, "up", 17)
            tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(180, 1900, int(dur * SR))) / SR)
            tone *= np.linspace(0, 1, len(tone)) ** 2
            place(buf, 0.6 * r + 0.18 * tone, t, 0.33)
        elif name == "swipe":
            sw = sweep_noise(0.34, 350, 6500, 0.9, "bell", 21)
            n = len(sw)
            pans = np.linspace(-0.9, 0.9, n)          # L -> R, follows the hand
            i = int(t * SR)
            ang = (pans + 1) * np.pi / 4
            buf[0, i:i + n] += sw * np.cos(ang) * 0.55
            buf[1, i:i + n] += sw * np.sin(ang) * 0.55
        elif name == "rev_hit":
            h = impact(0.5, 0.5)[::-1]
            place(buf, h, t - 0.5 + 0.03, 0.30)
        elif name == "cut_hit":
            place(buf, impact(0.7, 0.8), t, 0.55)
            place(buf, hat(True), t, 0.3)
        elif name == "end_impact":
            place(buf, endimp, t, 0.9)
        elif name == "ding":
            place(buf, ding(), t, 0.42)
        elif name == "final_hit":
            place(buf, impact(0.9, 1.3), t, 0.95)
            place(buf, ding(0.8), t, 0.25)
    return buf[:, :N]


# ----------------------------------------------------------------------------------
def main():
    os.makedirs(WORK, exist_ok=True)
    voice = voice_track()
    duck = duck_curve(voice)
    mus = music() * duck
    sfx = sfx_track()

    # Levels: voice is the reference (RMS -20 dBFS over speech); music sits ~12-14 dB under it
    # while the voice is present and swells when it is gone; SFX accent without masking.
    speech = voice[np.abs(voice) > db(-45)]
    v = voice * (db(-20.0) / np.sqrt(np.mean(speech ** 2)))
    mix = np.stack([v, v]) + mus * 0.50 + sfx * 0.42
    # tail fade to avoid a click at the very end
    f = int(0.05 * SR)
    mix[:, -f:] *= np.linspace(1, 0, f)
    peak = np.max(np.abs(mix))
    print("raw mix peak", round(20 * np.log10(peak), 2), "dBFS")
    wavfile.write(os.path.join(WORK, "mix_raw.wav"), SR, mix.T.astype(np.float32))
    np.save(os.path.join(WORK, "voice_tl.npy"), v.astype(np.float32))
    return mix


def master(target_i=-14.0, tp=-2.2, lra=9.0):
    import json
    raw = os.path.join(WORK, "mix_raw.wav")
    lim = os.path.join(WORK, "mix_lim.wav")
    out = os.path.join(WORK, "audio_final.wav")
    # tame the sharp SFX transients first so the loudness pass can reach the target with headroom
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw, "-af",
                    "alimiter=limit=0.55:attack=3:release=70:level=false", "-c:a", "pcm_f32le", lim], check=True)
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", lim, "-af",
                        f"loudnorm=I={target_i}:TP={tp}:LRA={lra}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    j = json.loads(p.stderr[p.stderr.rfind("{"):p.stderr.rfind("}") + 1])
    flt = (f"loudnorm=I={target_i}:TP={tp}:LRA={lra}:measured_I={j['input_i']}:"
           f"measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
           f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", lim, "-af", flt,
                    "-ar", str(SR), "-c:a", "pcm_s24le", out], check=True)
    print("measured before:", j["input_i"], "LUFS,", j["input_tp"], "dBTP")


if __name__ == "__main__":
    main()
    master()
