"""Audio mix for the film (M3): the code-synthesised theme over the clips' own river ambience.

Ambience = the audio of each accepted clip inside its edit window (`window_s`), placed at its film seconds (`film_s`)
from config/shots.json, with short fades at every cut. The end card has music only. Each stem is set to the RMS level
in config/music.json `mix` (dBFS) before summing; ambience peaks are held under `ambience_ceiling_db` by a block
limiter, and the sum under the music peak ceiling; final loudness is set later in the edit (loudnorm).
Writes `music.wav` (mono) and `mix-<orientation>.wav` (stereo) to `mix.out_dir`; prints one JSON line per file with sha256.
Usage: python3 tools/mix.py [--orientation landscape|portrait]
"""
import json
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import music  # noqa: E402

SHOTS = os.path.join(ROOT, "config", "shots.json")


class MixError(ValueError):
    pass


def rms_db(y):
    r = np.sqrt(np.mean(np.square(y))) if y.size else 0.0
    return 20 * np.log10(r) if r > 0 else float("-inf")


def to_level(y, target_db):
    """Scale `y` so its RMS is `target_db` dBFS. Silence stays silence."""
    level = rms_db(y)
    return y if level == float("-inf") else y * 10 ** ((target_db - level) / 20)


def limit(y, ceiling_db, sr, block_s):
    """Block limiter: each block gets the smallest gain needed in it and its neighbours, interpolated between block
    centres, so no sample ends above the ceiling and quiet passages are untouched. `y` is (n, channels)."""
    ceiling = 10 ** (ceiling_db / 20)
    size = max(1, int(block_s * sr))
    n_blocks = -(-len(y) // size)
    peaks = np.zeros(n_blocks * size)
    peaks[:len(y)] = np.max(np.abs(y), axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peaks.reshape(n_blocks, size).max(axis=1), 1e-12))
    padded = np.concatenate(([1.0], need, [1.0]))
    gain = np.minimum(np.minimum(padded[:-2], padded[1:-1]), padded[2:])
    centres = (np.arange(n_blocks) + 0.5) * size
    return y * np.interp(np.arange(len(y)), centres, gain)[:, None]


def edge_fade(seg, n):
    seg = seg.copy()
    n = min(n, len(seg) // 2)
    if n:
        ramp = np.linspace(0, 1, n)[:, None]
        seg[:n] *= ramp
        seg[-n:] *= ramp[::-1]
    return seg


def segments(shots_cfg, orientation):
    """(file, window_s, film_s) for each shot with an accepted clip, in film order. Windows must match film spans."""
    out = []
    for shot in shots_cfg["shots"]:
        clip = shot.get("accepted", {}).get(orientation)
        if not clip:
            raise MixError(f"{shot['id']}: no accepted {orientation} clip")
        (w0, w1), (f0, f1) = shot["window_s"], shot["film_s"]
        if abs((w1 - w0) - (f1 - f0)) > 1e-6:
            raise MixError(f"{shot['id']}: window {w1 - w0} s != film span {f1 - f0} s")
        out.append((clip, (w0, w1), (f0, f1)))
    out.sort(key=lambda s: s[2][0])
    for a, b in zip(out, out[1:]):
        if b[2][0] < a[2][1] - 1e-6:
            raise MixError(f"{b[0]} overlaps {a[0]}")
    return out


def decode(path, start, end, sr):
    """Stereo float32 audio of `path` between start and end seconds (ffmpeg)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", path,
                          "-vn", "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)


def ambience_track(parts, total_s, sr, edge_s):
    """parts = [(film_start_s, stereo array)]. Returns (n, 2) with each part faded at its edges."""
    n = int(round(total_s * sr))
    y = np.zeros((n, 2))
    for start, seg in parts:
        i = int(round(start * sr))
        seg = edge_fade(seg, int(edge_s * sr))
        k = min(len(seg), n - i)
        if k > 0:
            y[i:i + k] += seg[:k]
    return y


def mix(music_mono, ambience, sr, cfg):
    """Sum the two stems at their RMS levels (ambience measured where it plays), fade, and keep peaks under 0 dBFS."""
    m = cfg["mix"]
    if len(music_mono) != len(ambience):
        raise MixError(f"music {len(music_mono)} samples != ambience {len(ambience)}")
    mus = to_level(np.repeat(music_mono[:, None], 2, axis=1), m["music_db"])
    live = np.any(ambience != 0, axis=1)
    amb = ambience * (10 ** ((m["ambience_db"] - rms_db(ambience[live])) / 20) if live.any() else 0)
    # rare splashes in the clip audio sit 30 dB over its average; tame them so levelling does not clip
    amb = limit(amb, m["ambience_ceiling_db"], sr, m["limiter_block_s"])
    y = music.fade(mus + amb, sr, m["fade_in_s"], m["fade_out_s"])
    return limit(y, cfg["synth"]["peak_db"], sr, m["limiter_block_s"])


def report(path, y, sr):
    return {"file": os.path.basename(path), "seconds": round(len(y) / sr, 3), "channels": 1 if y.ndim == 1 else 2,
            "peak_dbfs": round(20 * np.log10(np.max(np.abs(y))), 2), "rms_dbfs": round(rms_db(y), 2),
            "sha256": music.sha256_file(path)}


def main(argv):
    orientation = argv[argv.index("--orientation") + 1] if "--orientation" in argv else "landscape"
    cfg = music.load()
    sr, total = cfg["sample_rate"], float(cfg["duration_s"])
    with open(SHOTS, encoding="utf-8") as f:
        shots_cfg = json.load(f)
    clips = os.path.join(ROOT, cfg["mix"]["clips_dir"])
    parts = [(film[0], decode(os.path.join(clips, clip), window[0], window[1], sr))
             for clip, window, film in segments(shots_cfg, orientation)]
    out_dir = os.path.join(ROOT, cfg["mix"]["out_dir"])
    theme = music.render(cfg)
    music_path = music.write_wav(os.path.join(out_dir, "music.wav"), theme, sr)
    y = mix(theme, ambience_track(parts, total, sr, cfg["mix"]["edge_fade_s"]), sr, cfg)
    mix_path = music.write_wav(os.path.join(out_dir, f"mix-{orientation}.wav"), y, sr)
    for path, data in ((music_path, theme), (mix_path, y)):
        print(json.dumps(report(path, data, sr)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
