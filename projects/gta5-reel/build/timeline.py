"""Single source of truth for the GTA 5 reel timing (frame-accurate, 30 fps).

Source timings come from fine audio analysis (5 ms RMS) of the raw clip plus the
user's script. Word timings are estimated by distributing syllables evenly over the
voiced intervals (checked against the energy peaks and the visible hand flick).
"""
FPS = 30
W, H = 1080, 1920
TOTAL_FRAMES = 420            # 14.0 s
END_START_F = 327             # end card starts here (10.9 s)

# (source_start_frame, source_end_frame_exclusive, output_start_frame)
SEGMENTS = [
    (147, 337, 0),            # A: voice onset 4.93s, ends 11.20s
    (351, 434, 190),          # B: sentence 2, up to "tomar"
    (440, 494, 273),          # C: "hater smartphone e play korba GTA 5"
]
END_FREEZE_SRC_FRAME = 493    # last used source frame; held behind the end card


def src_to_out(src_t):
    """Map a source time (s) to output time (s) using the segment table."""
    for f0, f1, o0 in SEGMENTS:
        if f0 / FPS - 1e-6 <= src_t <= f1 / FPS + 1e-6:
            return (src_t - f0 / FPS) + o0 / FPS
    raise ValueError(f"source time {src_t} is outside the kept segments")


def out_to_src_frame(out_f):
    """Output frame -> source frame index (end card freezes the last frame)."""
    for f0, f1, o0 in SEGMENTS:
        n = f1 - f0
        if o0 <= out_f < o0 + n:
            return f0 + (out_f - o0)
    return END_FREEZE_SRC_FRAME


def seg_start_times():
    return [o0 / FPS for _, _, o0 in SEGMENTS]


# --- Script (user supplied) with estimated word times in SOURCE seconds ---------
SCRIPT = ("Tomar jodi amar moto GTA 5 khelar jonno PC kenar plan thake, tahole tomar oi "
          "plan matha theke jhere fele dao! Cause ajke ami tomake dekhabo kibhabe tumi "
          "tomar hater smartphone e play korba GTA 5.")

SRC_WORDS = {
    "gta5": (6.19, 6.81), "pc": (7.44, 7.75), "plan": (8.07, 8.22),
    "matha": (9.64, 9.95), "theke": (9.95, 10.27),
    "jhere": (10.27, 10.58), "fele": (10.58, 10.89), "dao": (10.89, 11.20),
    "ajke": (12.19, 12.55), "dekhabo": (12.91, 13.35), "kibhabe": (13.35, 13.79),
    "tomar2": (14.08, 14.37), "hater": (14.70, 14.99), "smartphone": (14.99, 15.29),
    "e": (15.29, 15.43), "play": (15.43, 15.58), "korba": (15.58, 15.87),
    "gta5b": (15.87, 16.46),
}
FLICK_SRC = (10.58, 10.82)    # hand flick away from head, measured on the footage

O = src_to_out
FLICK = (O(FLICK_SRC[0]), O(FLICK_SRC[1]) + 0.08)    # swipe-off window (out s)

# Captions: (words [(text, color)], on, off) in OUTPUT seconds. Selective keywords only.
Y, C, P, WH = "yellow", "cyan", "purple", "white"
CAPTIONS = [
    ([("GTA 5", C)],                       O(6.19) - 0.04, O(6.81) + 0.06),
    ([("PC", C), ("KENAR PLAN", Y)],       O(7.32) - 0.04, O(8.22) + 0.10),
    ([("MATHA THEKE", Y)],                 O(9.64) - 0.04, O(10.27) + 0.03),
    ([("JHERE FELE DAO!", Y)],             O(10.27) + 0.03, FLICK[0] + 0.30),  # swipes off
    ([("AJKE", C), ("DEKHABO", Y)],        O(12.19) - 0.04, O(13.35) + 0.0),
    ([("KIBHABE?", C)],                    O(13.35), O(13.79) + 0.05),
    ([("TOMAR HATER", Y)],                 O(14.08) - 0.03, O(15.0) - 0.04),
    ([("SMARTPHONE", C), ("E", Y)],        O(14.99) - 0.04, O(15.43) + 0.0),
    ([("PLAY KORBA", Y)],                  O(15.43), O(15.87)),
    ([("GTA 5!", C)],                      O(15.87), END_START_F / FPS - 0.03),
]

# Graphics events (output seconds)
HOOK_IN, HOOK_OUT = 0.10, 2.25
TAG_IN, TAG_OUT = 2.35, END_START_F / FPS - 0.10
PC_CARD_IN = O(7.44) - 0.05
PHONE_CARD_IN = O(14.99) - 0.04
END_TEXT1_IN, END_TEXT2_IN, END_TAG_IN = 11.05, 11.27, 11.75
UNDERLINE_IN = O(12.19) - 0.04

# Sound design events (output seconds): (name, time)
SFX = [
    ("impact", 0.10), ("whoosh_in", 0.02),
    ("pop", O(6.19) - 0.04), ("pop", O(7.32) - 0.04), ("card_in", PC_CARD_IN),
    ("pop", O(9.64) - 0.04), ("pop", O(10.27) + 0.03),
    ("pop", TAG_IN), ("tick", UNDERLINE_IN + 0.05),
    ("riser", 3.85),                         # rises until the swipe
    ("swipe", FLICK[0]), ("rev_hit", FLICK[0]),
    ("cut_hit", 190 / FPS),
    ("pop", O(12.19) - 0.04), ("pop", O(13.35)),
    ("pop", O(14.08) - 0.03), ("card_in", PHONE_CARD_IN), ("pop", O(14.99) - 0.04),
    ("pop", O(15.43)), ("pop", O(15.87)),
    ("end_impact", END_START_F / FPS), ("ding", END_START_F / FPS + 0.05),
    ("pop", END_TEXT1_IN), ("pop", END_TEXT2_IN), ("pop", END_TAG_IN),
    ("final_hit", 13.72),
]
MUSIC_DROP = (FLICK[1] + 0.02, 190 / FPS)    # brief music dropout before the cut

# Zoom keyframes are defined in video.py
if __name__ == "__main__":
    n = sum(f1 - f0 for f0, f1, _ in SEGMENTS)
    print("kept frames", n, "=", round(n / FPS, 3), "s; end card", TOTAL_FRAMES - END_START_F, "frames")
    print("flick out window", [round(x, 3) for x in FLICK])
    for words, a, b in CAPTIONS:
        print(f"{a:6.2f}-{b:6.2f}  {' '.join(t for t, _ in words)}")
