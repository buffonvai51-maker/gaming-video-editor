#!/usr/bin/env bash
# Print a compact summary of a video file: duration, resolution, fps, codecs, audio.
# Usage: probe.sh <video-file>
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: probe.sh <video-file>" >&2
  exit 2
fi
if [ ! -f "$1" ]; then
  echo "error: file not found: $1" >&2
  exit 1
fi
command -v ffprobe >/dev/null || { echo "error: ffprobe not installed" >&2; exit 1; }

ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels \
  -of default=noprint_wrappers=1 "$1"
