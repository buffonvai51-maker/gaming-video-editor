# gaming-video-editor

A repeatable workflow for editing gaming videos with Claude.

## Layout

```
.claude/skills/video-editing/   The video-editing skill (loaded automatically by Claude Code in this repo)
  SKILL.md                      Workflow and rules Claude follows
  scripts/probe.sh              Inspect a video (duration, resolution, audio)
  scripts/silence_cuts.py       Detect silence -> edit list -> render the cut
  scripts/export_preset.sh      Export for youtube (16:9), shorts (9:16) or square (1:1)
projects/_template/             Copy this folder for each new video
  brief.md                      Goal, length, platform, style notes
  raw/                          Source footage (not committed)
  assets/                       Music, overlays, fonts, logos
  work/                         Edit lists and intermediate renders (not committed)
  output/                       Final exports (not committed)
```

## Starting a new video

1. Copy `projects/_template/` to `projects/<video-name>/`.
2. Fill in `brief.md`.
3. Put footage in `raw/`.
4. Open this repo in Claude Code and ask it to edit the video. The `video-editing` skill
   is picked up automatically.

Requires `ffmpeg` and `ffprobe`.

## What the skill does today

Removes silence and dead air via a reviewable edit list, then exports for the target platform.
Captions, zooms, highlight detection, music and brand styling are not built yet.

Large media files are git-ignored on purpose. Keep footage and exports outside git (or use Git LFS
if you want them versioned).
