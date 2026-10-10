---
name: video-editing
description: Edit gaming videos from raw footage with ffmpeg: cut silence and dead air, trim to an edit list, and export for YouTube, Shorts or square. Use when the user asks to edit, trim, cut, clean up or export a video in this repository.
---

# Video editing

Edit footage in a project folder by building a reviewable edit list, then rendering it with ffmpeg.
Everything here is repeatable: the same inputs and settings give the same output.

> Defaults below were chosen without the user's reference workflow. If the user's brief or
> instructions conflict with a default, follow the user and update this file.

## Project layout

Each video lives in `projects/<video-name>/` (copy `projects/_template/`):

- `brief.md`: goal, platform, length, style. Read this first.
- `raw/`: source footage. Never modify or overwrite these files.
- `assets/`: music, overlays, fonts, logos.
- `work/`: edit lists, transcripts, intermediate renders.
- `output/`: final exports.

Media files are git-ignored. Do not commit footage or exports.

## Workflow

1. **Read the brief.** If `brief.md` is empty or missing key fields (platform, target length,
   edits wanted), ask the user before editing.
2. **Inspect the footage.** Run `scripts/probe.sh <file>` for each source. Note duration,
   resolution, frame rate and whether audio exists.
3. **Build an edit list.** For silence and dead-air removal run:
   `python3 scripts/silence_cuts.py detect <raw file> projects/<name>/work/edit_list.json`
   This writes the segments to keep. Tune with `--noise` (dB, default -35),
   `--min-silence` (seconds, default 0.6) and `--pad` (seconds kept around speech, default 0.15).
   Gaming footage with loud game audio may need a lower threshold (for example `--noise -45`),
   or silence detection may not be the right tool; say so rather than forcing it.
4. **Review before rendering.** Unless the brief says to edit directly, show the user the
   summary (segments kept, total length) and ask for approval. They can hand-edit the JSON.
5. **Render.** `python3 scripts/silence_cuts.py render <raw file> <edit_list.json> projects/<name>/work/cut.mp4`
6. **Export for the platform.** `scripts/export_preset.sh <cut.mp4> projects/<name>/output/<name>.mp4 <youtube|shorts|square>`
   Match the preset to the brief. Default to `youtube` if none is stated.
7. **Verify.** Run `scripts/probe.sh` on the output. Check the duration matches the edit list,
   audio is present, and the resolution matches the preset. Report the result to the user.

## Edit list format

```json
{"source": "raw/clip.mp4", "duration": 123.4,
 "segments": [{"start": 0.0, "end": 12.3}, {"start": 15.0, "end": 40.2}]}
```

Segments are the parts to keep, in order, in seconds. For manual cuts (highlights only, remove a
section), write the JSON directly instead of running `detect`.

## Rules

- Never overwrite files in `raw/`. Write results to `work/` or `output/`.
- Cuts re-encode for frame accuracy. Do not use stream copy for cuts.
- Check `ffmpeg` and `ffprobe` exist before starting. If missing, say so and stop.
- Before running something long (multi-hour footage), tell the user the expected cost.
- If silence detection finds almost nothing, or removes most of the video, stop and report
  instead of rendering a bad result.

## Not built yet

These need the user's input before they are added, so do not improvise them:

- Captions (needs a speech-to-text tool such as Whisper and a caption style).
- Zooms, highlight detection, b-roll, music mixing, transitions.
- Brand fonts, colors and caption styling.
