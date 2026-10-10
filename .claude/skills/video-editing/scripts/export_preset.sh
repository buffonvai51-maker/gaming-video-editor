#!/usr/bin/env bash
# Re-encode a video for a target platform preset.
# Usage: export_preset.sh <input> <output> <preset>
# Presets:
#   youtube   1920x1080 (16:9), letterboxed if needed
#   shorts    1080x1920 (9:16), center-cropped to fill
#   square    1080x1080 (1:1), center-cropped to fill
set -euo pipefail

if [ $# -ne 3 ]; then
  echo "usage: export_preset.sh <input> <output> <youtube|shorts|square>" >&2
  exit 2
fi
in="$1"; out="$2"; preset="$3"
[ -f "$in" ] || { echo "error: file not found: $in" >&2; exit 1; }

case "$preset" in
  youtube)
    vf="scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1" ;;
  shorts)
    vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1" ;;
  square)
    vf="scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,setsar=1" ;;
  *)
    echo "error: unknown preset '$preset' (use youtube, shorts or square)" >&2; exit 2 ;;
esac

ffmpeg -y -hide_banner -loglevel error -i "$in" -vf "$vf" \
  -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart "$out"
echo "Wrote $out ($preset)"
