# GTA 5 on phone: Reel storyboard and edit list (DRAFT for approval)

Company: The Xaad Universe | Type: talking head | Format: 9:16, 1080x1920, 30fps, H.264
Source: `raw/WhatsApp Video 2026-10-10 at 3.22.45 PM.mp4` (19.22s)
Reference studied: `How to edit viral reels in After Effects.mp4` (14.1s kinetic type + object motion graphics, hard cuts on beats, spring text reveals, spotlight sweeps)

## What the footage actually contains

| Finding | Detail | Impact |
|---|---|---|
| Tiny source | 368x496 (3:4), WhatsApp-compressed, variable frame rate | 1080x1920 is a 2.9x to 3.9x upscale. Video will be soft; graphics will be crisp. |
| Speech window | Measured from audio: speech runs src 4.9s to 16.4s (11.5s). 0 to 4.8s and 16.5 to 19.2s are a flat noise floor near -28 dB. | Cutting both ends removes about 7.5s. Default -35 dB silence detection found nothing because the noise floor is above it. |
| Natural pauses | Only two real mid-speech pauses: src 11.25 to 11.62 and 14.42 to 14.65 | Tightened to about 0.1s each. |
| Mouth moves with no speech audio | Frames at src 2.5 to 4.5s show him speaking, but audio there is a flat floor | Needs your confirmation before I cut it. |
| Hand gesture | Large open-palm gesture held at right edge src 15.0 to 16.5s | Likely the "jhere fele dao" moment. Not verified. |
| Missing | No transcript possible here (speech-to-text cannot be installed or downloaded). No GTA footage, music, SFX, or Montserrat/Anton fonts in the repo. | Captions, music, SFX and fonts need your input or fallbacks (see Open decisions). |

## Edit list (source to output)

| # | Source range | Output range | Length | Note |
|---|---|---|---|---|
| A | 4.80 to 11.25 | 0.00 to 6.45 | 6.45s | Starts 0.1s before first word |
| B | 11.62 to 14.42 | 6.45 to 9.25 | 2.80s | Hard cut over 0.37s pause |
| C | 14.65 to 16.55 | 9.25 to 11.15 | 1.90s | Includes the open-palm gesture |
| End card | freeze/slow push on src 16.55 | 11.15 to 14.15 | 3.00s | Voice finished; music and SFX only |

Result: **14.15s**. See Open decision 1 about the 19s target.
Audio joins use 2-frame crossfades. Video is conformed to constant 30fps first.

## Beat-by-beat storyboard (output time)

| Time | Picture | Graphics | Captions (slots, text pending script) | Sound |
|---|---|---|---|---|
| 0.00 to 2.00 HOOK | Slow push-in 1.00x to 1.05x (ease-out) | Hook title springs in at 0.10s (scale 0 to 1.12 to 1.0 in 0.4s). Proposed text from your goal: "GTA 5 ON YOUR PHONE" with "NO PC" in cyan. Replace with his actual hook if different. | Caption 1 on first emphasized word (src 4.9s) | Low impact hit at 0.10, whoosh on title, music in with filter sweep |
| 2.00 to 4.40 | Held framing, 2-frame punch-in cut at 3.2s for pace | Small spring-in brand tag "THE XAAD UNIVERSE" top safe area, stays through 11.0 | Captions 2 and 3 at emphasis peaks (src 6.5s, 7.0s) | Soft pop per caption, music ducks under voice |
| 4.40 to 6.45 | Subtle alternating 1.00x/1.04x scale per phrase | Spring-scale icon card (phone, from the on-screen concept) | Caption 4 at src 7.9s | Whoosh in, pop |
| 6.45 to 9.25 | Hard cut at 6.45 | Yellow underline sweep or step badge, spring entry | Captions 5 and 6 at src 12.2s and 13.5s | Cut accent, riser starts at 8.4 |
| 9.25 to 10.4 | Gesture builds | Object to throw away (e.g. "PC" tag) held in frame | Caption 7 | Riser peaks |
| ~10.4 to 10.9 SWIPE | Hand swipe | **Motion-blur swipe-off**: object and caption slide right off frame with 12-sample directional blur in 5 frames, synced to the hand. Timing estimated from the gesture at src 15.4 to 16.0; to be locked once you confirm the word's time. | none during swipe | Swipe whoosh plus short reverse hit |
| 10.9 to 11.15 | Settle | Clear frame | none | Beat of near-silence in the music (0.15s) for contrast |
| 11.15 to 14.15 END CARD | Video dimmed and blurred behind, slow push | "FOLLOW FOR MORE GAMING TIPS!" springs in (Anton, yellow with purple stroke, "GAMING TIPS" cyan), brand tag centered | none | Impact plus ding, music swells, final hit at 14.0 and 0.1s tail |

Caption style: Anton uppercase, yellow #FFD700 fill, deep purple #7F00FF stroke, one keyword in cyan #00C6FF, 1 to 3 words at a time, spring pop (scale 0.7 to 1.1 to 1.0 in 0.25s), lower-middle safe area (about y 1300 to 1500), clear of the top 150px and bottom 250px platform UI zones. Selective: emphasis words only, not every word.

## Look and audio treatment

- Picture: conform to 30fps, mild denoise, unsharp, light contrast/saturation lift, fine film grain to hide upscale softness. Cyan/purple accent glows on graphics only.
- Voice: high-pass 80Hz, moderate noise reduction (speech sits only 10 to 15 dB above the floor, so not aggressive), gentle compression, de-ess if needed, normalize.
- Music: no track provided, so an original synthesized loop (about 124 BPM) unless you supply one. Sidechain-ducked about 12 to 14 dB under voice, swells on the end card.
- SFX: synthesized whooshes, impacts, pops, riser, swipe, ding.
- Master: about -14 LUFS integrated, true peak at or below -1.5 dBTP, checked by measurement.
- Export: 1080x1920, 30fps CFR, H.264 High, yuv420p, CRF 18, AAC 192k, faststart.

## Build and QA plan (after approval)

1. Conform and cut per edit list, then verify durations by probe.
2. Render graphics as RGBA frame sequences (springs computed analytically, motion blur via multi-sample accumulation) and composite.
3. Build voice chain and synthesized music/SFX, mix with ducking, loudness-measure.
4. Render the full video, extract frames at every beat (0.1s, 1.0s, 3.2s, 6.45s, swipe, end card) and inspect for crop, overlap, safe-zone, font and color errors.
5. Fix issues, re-render, final probe: 1080x1920, 30fps, H.264, duration, audio present, loudness and peak.

## Open decisions (need your answer before I build)

1. **Length.** Real content is about 11.2s of speech, so the honest cut is 14.15s. Hitting exactly 19s means adding about 4.85s of content I don't have (for example your GTA-on-phone gameplay clips or screenshots). Options: (a) 14.15s tight cut (recommended for retention), (b) 19s using extra clips you add to `assets/`, (c) 19s by keeping dead lead-in footage (not recommended).
2. **Script.** Paste his Banglish lines (rough is fine) and the exact "jhere fele dao" line so I can time captions and lock the swipe. I cannot transcribe the audio here.
3. **Layout for the small source.** (A) Fit-width: video fills 1080 wide (1456 tall) over a purple-to-black brand background with banner and caption zones. Keeps his hands in frame. Recommended. (B) Full-bleed crop: sharper-looking face fill, but crops about 24% of the width and cuts off the right-hand gesture at 15 to 16.5s unless I pan.
4. **Pre-speech footage.** OK to cut src 0 to 4.8s, since there is no speech audio there (though his mouth moves)? If there was speech that the audio lost, tell me.
5. **Fonts, music, CTA.** Upload Anton and Montserrat Black TTFs to `projects/gta5-reel/assets/fonts/` (this workspace cannot download them). Without them I fall back to Poppins Bold, which is wider and not condensed. Upload a licensed music track if you want a specific one. Is the CTA on-screen text only, or does he say it?
