# gaming-video-editor

A repeatable workflow for editing gaming videos with Claude.

## Layout

```
skills/video-editing/SKILL.md   Reusable editing skill (draft, finalized once the reference workflow is reviewed)
projects/_template/             Copy this folder for each new video
  brief.md                      Goal, length, platform, style notes
  raw/                          Source footage (not committed)
  assets/                       Music, overlays, fonts, logos
  work/                         Transcripts, edit lists, intermediate renders (not committed)
  output/                       Final exports (not committed)
scripts/                        Helper scripts (ffmpeg wrappers, etc.)
```

## Starting a new video

1. Copy `projects/_template/` to `projects/<video-name>/`.
2. Fill in `brief.md`.
3. Put footage in `raw/`.
4. Ask Claude to edit it using the video-editing skill.

Large media files are git-ignored on purpose. Keep footage and exports outside git (or use Git LFS if you want them versioned).
