#!/usr/bin/env python3
"""Step 1: conform source to 30fps, cut to the approved edit list, clean the voice.

Outputs (in ../work):
  conf_mci.mp4   source conformed to constant 30fps with motion interpolation
  cut_src.mp4    picture for the speech segments + 1s of tail footage (368x496, near-lossless)
  voice.wav      cut + cleaned voice, 48k mono, padded to 14.0s (silent after speech)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import timeline as T

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW = os.path.join(ROOT, "raw", "WhatsApp Video 2026-10-10 at 3.22.45 PM.mp4")
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + r.stderr[-2000:])


def conform():
    out = os.path.join(WORK, "conf_mci.mp4")
    if not os.path.exists(out):
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", RAW, "-an",
             "-vf", "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
             "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", out])
    return out


def cut_picture(conf):
    ranges = list(T.SEGMENTS) + [(T.SRC_FIRST_TAIL, T.SRC_FIRST_TAIL + T.TAIL_SRC_FRAMES)]
    parts, labels = [], []
    for i, (a, b) in enumerate(ranges):
        parts.append(f"[0:v]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    parts.append("".join(labels) + f"concat=n={len(ranges)}:v=1:a=0,fps=30[v]")
    out = os.path.join(WORK, "cut_src.mp4")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", conf,
         "-filter_complex", ";".join(parts), "-map", "[v]",
         "-c:v", "libx264", "-crf", "6", "-pix_fmt", "yuv420p", out])
    return out


def cut_voice():
    parts, labels = [], []
    fade = 0.012
    for i, (a, b) in enumerate(T.SEGMENTS):
        s, e = a / T.FPS, b / T.FPS
        d = e - s
        parts.append(
            f"[0:a]atrim=start={s:.5f}:end={e:.5f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade},afade=t=out:st={d - fade:.5f}:d={fade}[a{i}]")
        labels.append(f"[a{i}]")
    chain = (
        "pan=mono|c0=0.5*c0+0.5*c1,"
        "highpass=f=85,"
        "afftdn=nr=12:nf=-28:nt=w,"
        "equalizer=f=250:t=q:w=1:g=-2,"
        "equalizer=f=3200:t=q:w=1:g=3,"
        "acompressor=threshold=-30dB:ratio=4:attack=5:release=80:makeup=7,"
        "alimiter=limit=0.89:level=0,"
        f"apad=whole_dur={T.TOTAL_FRAMES / T.FPS},atrim=0:{T.TOTAL_FRAMES / T.FPS}"
    )
    parts.append("".join(labels) + f"concat=n={len(T.SEGMENTS)}:v=0:a=1,{chain}[a]")
    out = os.path.join(WORK, "voice.wav")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", RAW,
         "-filter_complex", ";".join(parts), "-map", "[a]", "-ar", "48000",
         "-c:a", "pcm_f32le", out])
    return out


if __name__ == "__main__":
    conf = conform()
    print("conformed:", conf)
    print("cut picture:", cut_picture(conf))
    print("voice:", cut_voice())
