import sys, subprocess, numpy as np
from scipy.io import wavfile
from scipy.signal import stft, istft
from scipy.ndimage import uniform_filter
sys.path.insert(0, __file__.rsplit("/",1)[0])
from timeline import *

P = sys.argv[1]                       # project dir
SR = 48000

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.exit(r.stderr[-1500:])
    return r.stderr

run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",f"{P}/{RAW}","-vn","-ac","1","-ar",str(SR),
     "-c:a","pcm_f32le",f"{P}/work/src_mono.wav"])
sr, x = wavfile.read(f"{P}/work/src_mono.wav"); x = x.astype(np.float32)

# --- spectral noise reduction, noise profile from the speech-free lead-in (0.3-4.6 s)
f, t, Z = stft(x, fs=SR, nperseg=2048, noverlap=1536, window="hann")
pw = np.abs(Z)**2
nf = (t > 0.3) & (t < 4.6)
N = pw[:, nf].mean(axis=1)
alpha, gmin = 1.7, 0.18
G = np.sqrt(np.maximum(pw - alpha*N[:, None], 0) / (pw + 1e-12))
G = uniform_filter(np.maximum(G, gmin), size=(3, 3))
_, y = istft(Z * G, fs=SR, nperseg=2048, noverlap=1536, window="hann")
y = y[:len(x)].astype(np.float32)

def rms_db(a): return 20*np.log10(np.sqrt(np.mean(a**2)) + 1e-9)
print(f"noise floor  before {rms_db(x[int(1*SR):int(4*SR)]):.1f} dB  after {rms_db(y[int(1*SR):int(4*SR)]):.1f} dB")
print(f"speech level before {rms_db(x[int(5*SR):int(6*SR)]):.1f} dB  after {rms_db(y[int(5*SR):int(6*SR)]):.1f} dB")

# --- cut per edit list, 12 ms dip-fades at every join (no timeline change)
out = np.zeros(int(round(TOTAL*SR)), np.float32)
fade = int(0.012*SR)
for _, a, b, o in SEGMENTS:
    seg = y[int(round(a*SR)):int(round(b*SR))].copy()
    seg[:fade] *= np.linspace(0, 1, fade)
    seg[-fade:] *= np.linspace(1, 0, fade)
    i = int(round(o*SR)); out[i:i+len(seg)] = seg
wavfile.write(f"{P}/work/voice_cut.wav", SR, out)

# --- tone, dynamics
chain = ("highpass=f=85,equalizer=f=220:t=q:w=1:g=-1.5,equalizer=f=3200:t=q:w=1:g=2.5,"
         "equalizer=f=9000:t=h:w=0.7:g=1.5,"
         "acompressor=threshold=0.07:ratio=3:attack=6:release=140:makeup=3,alimiter=limit=0.9")
run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",f"{P}/work/voice_cut.wav","-af",chain,
     "-c:a","pcm_f32le",f"{P}/work/voice_proc.wav"])
log = run(["ffmpeg","-hide_banner","-nostats","-i",f"{P}/work/voice_proc.wav","-af","ebur128=peak=true","-f","null","-"])
for l in log.splitlines()[-14:]:
    if any(k in l for k in ("I:","Peak:")): print(l.strip())
