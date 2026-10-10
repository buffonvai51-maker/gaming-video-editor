---
name: video-editing
description: Edit gaming videos from raw footage using ffmpeg, following the project's brief. DRAFT, to be finalized.
---

# Video editing (draft)

Status: skeleton only. The workflow below is a placeholder until the reference
editing workflow has been reviewed and the open questions are answered.

## Inputs
- A project folder copied from `projects/_template/` with `brief.md` filled in.
- Source footage in `raw/`.

## Workflow (to be confirmed)
1. Read `brief.md`.
2. Inspect footage (duration, resolution, frame rate, audio) with ffprobe.
3. Analyze: transcript, silence detection, highlight candidates. (TBD)
4. Propose or apply an edit list. (TBD, depends on approval preference)
5. Render to `output/` in the target aspect ratio and format.
6. Report what changed and where the file is.

## Open questions
- Which edits are automatic (silence cuts, captions, zooms, music)?
- Approve an edit list first, or edit directly?
- Caption and brand style.
- Where should this run (cloud workspace, local machine, both)?
