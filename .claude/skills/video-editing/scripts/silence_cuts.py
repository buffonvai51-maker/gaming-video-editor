#!/usr/bin/env python3
"""Detect silence in a video and build an edit list of the parts worth keeping.

Usage:
  silence_cuts.py detect <input> <edit_list.json> [--noise -35] [--min-silence 0.6] [--pad 0.15]
  silence_cuts.py render <input> <edit_list.json> <output> [--crf 20]

`detect` writes an edit list (JSON) you can review and hand-edit before rendering.
`render` cuts the kept segments and joins them, re-encoding so cuts are frame accurate.

Edit list format:
  {"source": "raw/clip.mp4", "duration": 123.4,
   "segments": [{"start": 0.0, "end": 12.3}, ...]}
"""
import argparse
import json
import re
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"error: could not read duration of {path}: {r.stderr.strip()}")
    return float(r.stdout.strip())


def has_audio(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path])
    return bool(r.stdout.strip())


def detect(args):
    duration = probe_duration(args.input)
    if not has_audio(args.input):
        sys.exit("error: input has no audio stream, so silence cannot be detected")

    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", args.input,
             "-af", f"silencedetect=noise={args.noise}dB:d={args.min_silence}",
             "-f", "null", "-"])
    log = r.stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", log)]

    # A silence still open at EOF has a start but no end.
    if len(starts) > len(ends):
        ends.append(duration)
    silences = list(zip(starts, ends))

    # Keep everything between silences, padded so words aren't clipped.
    segments, cursor = [], 0.0
    for s, e in silences:
        seg_end = min(duration, s + args.pad)
        if seg_end - cursor > 0.05:
            segments.append({"start": round(max(0.0, cursor), 3),
                             "end": round(seg_end, 3)})
        cursor = max(0.0, e - args.pad)
    if duration - cursor > 0.05:
        segments.append({"start": round(cursor, 3), "end": round(duration, 3)})

    # Merge segments that overlap after padding.
    merged = []
    for seg in segments:
        if merged and seg["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], seg["end"])
        else:
            merged.append(seg)

    kept = sum(s["end"] - s["start"] for s in merged)
    out = {"source": args.input, "duration": round(duration, 3), "segments": merged}
    with open(args.edit_list, "w") as f:
        json.dump(out, f, indent=2)
    print(f"{len(silences)} silences found; keeping {len(merged)} segments, "
          f"{kept:.1f}s of {duration:.1f}s ({100 * kept / duration:.0f}%). "
          f"Edit list: {args.edit_list}")


def render(args):
    with open(args.edit_list) as f:
        data = json.load(f)
    segs = data["segments"]
    if not segs:
        sys.exit("error: edit list has no segments")
    audio = has_audio(args.input)

    parts, labels = [], []
    for i, s in enumerate(segs):
        parts.append(f"[0:v]trim=start={s['start']}:end={s['end']},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
        if audio:
            parts.append(f"[0:a]atrim=start={s['start']}:end={s['end']},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
    n = len(segs)
    if audio:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[v][a]")
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=0[v]")
        maps = ["-map", "[v]"]

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", args.input,
           "-filter_complex", ";".join(parts), *maps,
           "-c:v", "libx264", "-crf", str(args.crf), "-preset", "medium",
           "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", args.output]

    r = run(cmd)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{r.stderr}")
    print(f"Wrote {args.output} ({probe_duration(args.output):.1f}s)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect")
    d.add_argument("input")
    d.add_argument("edit_list")
    d.add_argument("--noise", type=float, default=-35, help="silence threshold in dB")
    d.add_argument("--min-silence", type=float, default=0.6, help="min silence length (s)")
    d.add_argument("--pad", type=float, default=0.15, help="padding kept around speech (s)")
    d.set_defaults(fn=detect)

    r = sub.add_parser("render")
    r.add_argument("input")
    r.add_argument("edit_list")
    r.add_argument("output")
    r.add_argument("--crf", type=int, default=20)
    r.set_defaults(fn=render)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
