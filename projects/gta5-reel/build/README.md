# GTA 5 reel build

Current pipeline (use these):
- `timeline.py`  single source of truth for timing, captions and SFX events
- `audio.py`     voice cleanup, synthesized music and SFX, ducking, loudness master
- `video.py`     frame renderer; `--render` then `--mux OUT.mp4`

Run order: `python3 audio.py && python3 video.py --render && python3 video.py --mux ../output/gta5-reel.mp4`

Older, superseded versions kept for reference only (not used by the current render):
`01_cut.py`, `02_audio.py`, `03_video.py`, `reel_voice.py`, `reel_music.py`, `reel_video.py`
