"""Original theme synthesised by code (decision 0001, KM5): numpy only, no samples, deterministic.

Everything comes from config/music.json: tempo, key, chord progression, sections (density and register), the
"fare paid" motif and the synthesis settings. One cue covers the whole film (`duration_s`).
Layers: a soft detuned sine pad on each chord, a Karplus-Strong plucked root on the first beat of each chord in
denser sections, and kalimba notes on chord tones where a seeded random draw falls under the section density.
The motif plays alone (arpeggio cleared around it). A noise-tail convolution adds room, then a fade and a peak limit.
Same config gives the same WAV bytes (unit test).
Usage: python3 tools/music.py [--out media/audio/music.wav]
"""
import hashlib
import json
import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config", "music.json")
PITCH = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


class MusicError(ValueError):
    pass


def frequency(name):
    """'A4' -> 440.0, 'F#5' -> 739.99 (scientific octave)."""
    letter, octave = name[:-1], name[-1]
    if letter not in PITCH or not octave.isdigit():
        raise MusicError(f"bad note {name!r}")
    midi = 12 * (int(octave) + 1) + PITCH[letter]
    return 440.0 * 2 ** ((midi - 69) / 12)


def chord_notes(chord):
    """'D' -> ['D', 'F#', 'A'], 'Bm' -> ['B', 'D', 'F#'] (triads only)."""
    minor = chord.endswith("m")
    root = chord[:-1] if minor else chord
    if root not in PITCH:
        raise MusicError(f"bad chord {chord!r}")
    names = list(PITCH)
    steps = (0, 3, 7) if minor else (0, 4, 7)
    return [names[(PITCH[root] + s) % 12] for s in steps]


def section_at(sections, t):
    for s in sections:
        if s["start_s"] <= t < s["end_s"]:
            return s
    raise MusicError(f"no section covers {t:.2f} s")


def check_sections(cfg):
    """Sections must tile 0..duration_s with no gap or overlap."""
    edge = 0.0
    for s in cfg["sections"]:
        if abs(s["start_s"] - edge) > 1e-9 or s["end_s"] <= s["start_s"]:
            raise MusicError(f"section {s['name']} does not continue at {edge}")
        edge = s["end_s"]
    if abs(edge - cfg["duration_s"]) > 1e-9:
        raise MusicError(f"sections end at {edge}, cue is {cfg['duration_s']} s")


def kalimba(f, seconds, sr, p, amp=1.0):
    t = np.arange(int(seconds * sr)) / sr
    y = np.zeros_like(t)
    for ratio, a in p["partials"]:
        # upper partials die faster: a tine strike, then a round tone
        y += a * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t / (p["decay_s"] / ratio ** 0.7))
    return amp * p["amp"] * y * np.minimum(1.0, t / (p["attack_ms"] / 1000))


def pluck(f, seconds, sr, p, rng):
    """Karplus-Strong: a noise buffer one period long, averaged and decayed in blocks of at most one period."""
    n = int(seconds * sr)
    period = max(2, int(round(sr / f)))
    buf = rng.uniform(-1, 1, period)
    for _ in range(int(round((1 - p["brightness"]) * 4))):
        buf = 0.5 * (buf + np.roll(buf, 1))
    a = period + 1
    y = np.zeros(a + n)
    y[1:a] = buf
    i = a
    while i < a + n:
        k = min(period, a + n - i)
        y[i:i + k] = p["decay"] * 0.5 * (y[i - period:i - period + k] + y[i - period - 1:i - period - 1 + k])
        i += k
    return p["amp"] * y[a:]


def pad(notes, seconds, sr, p):
    t = np.arange(int(seconds * sr)) / sr
    y = np.zeros_like(t)
    for f in notes:
        for cents in (-p["detune_cents"], p["detune_cents"]):
            y += 0.5 * np.sin(2 * np.pi * f * 2 ** (cents / 1200) * t)
    hold = seconds - p["release_s"]
    env = np.clip(np.minimum(t / p["attack_s"], 1 - (t - hold) / p["release_s"]), 0, 1)
    return p["amp"] * y * env


def place(track, sound, t, sr):
    i = int(round(t * sr))
    k = min(len(sound), len(track) - i)
    if k > 0:
        track[i:i + k] += sound[:k]


def reverb(y, sr, p, rng):
    """FFT convolution with an exponentially decaying noise response (seeded)."""
    n_ir = int(p["length_s"] * sr)
    t = np.arange(n_ir) / sr
    ir = rng.standard_normal(n_ir) * np.exp(-t / p["decay_s"])
    ir[: int(p["predelay_ms"] / 1000 * sr)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    n = len(y) + n_ir - 1
    m = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(y, m) * np.fft.rfft(ir, m), m)[: len(y)]
    return (1 - p["wet"]) * y + p["wet"] * wet


def motif_span(cfg):
    m = cfg["motif"]
    return m["at_s"], m["at_s"] + len(m["notes"]) * m["note_s"]


def render(cfg):
    """The full cue as a mono float array at cfg['sample_rate']."""
    check_sections(cfg)
    s, sr, dur = cfg["synth"], cfg["sample_rate"], float(cfg["duration_s"])
    rng = np.random.default_rng(cfg["seed"])
    tail = s["reverb"]["length_s"] + s["kalimba"]["decay_s"] * 3
    y = np.zeros(int((dur + tail) * sr))
    beat = 60.0 / cfg["tempo_bpm"]
    bar = beat * s["beats_per_chord"]
    step = beat / s["steps_per_beat"]
    clear_a, clear_b = motif_span(cfg)
    clear_a, clear_b = clear_a - s["motif"]["clear_s"], clear_b + s["motif"]["clear_s"]
    n_bars = int(np.ceil(dur / bar))
    for b in range(n_bars):
        t0 = b * bar
        chord = cfg["progression"][b % len(cfg["progression"])]
        names = chord_notes(chord)
        sec = section_at(cfg["sections"], t0)
        p = s["pad"]
        place(y, pad([frequency(n + str(p["octave"])) for n in names], min(bar, dur - t0) + p["release_s"], sr, p), t0, sr)
        if sec["density"] >= s["pluck"]["min_density"]:
            place(y, pluck(frequency(names[0] + str(s["pluck"]["octave"])), s["pluck"]["length_s"], sr, s["pluck"], rng),
                  t0, sr)
        octave = s["register_octave"][sec["register"]]
        for k in range(s["beats_per_chord"] * s["steps_per_beat"]):
            t = t0 + k * step
            # draw every step so a change in one section never shifts the notes of another
            hit, pick, up = rng.random(), rng.integers(len(names)), rng.random()
            if t >= dur or clear_a <= t < clear_b:
                continue
            if k == 0 or hit < section_at(cfg["sections"], t)["density"]:
                o = octave + (1 if up < s["kalimba"]["upper_octave_chance"] else 0)
                place(y, kalimba(frequency(names[pick] + str(o)), s["kalimba"]["decay_s"] * 3, sr, s["kalimba"]), t, sr)
    m = cfg["motif"]
    for i, note in enumerate(m["notes"]):
        place(y, kalimba(frequency(note), s["kalimba"]["decay_s"] * 3, sr, s["kalimba"], s["motif"]["amp"]),
              m["at_s"] + i * m["note_s"], sr)
    y = reverb(y, sr, s["reverb"], rng)[: int(dur * sr)]
    return finish(y, sr, cfg["mix"]["fade_in_s"], cfg["mix"]["fade_out_s"], s["peak_db"])


def fade(y, sr, fade_in_s, fade_out_s):
    """Linear fade in, squared fade out; works on mono (n,) and multichannel (n, c) arrays."""
    y = y.copy()
    a, b = int(fade_in_s * sr), int(fade_out_s * sr)
    shape = (-1,) + (1,) * (y.ndim - 1)
    if a:
        y[:a] *= np.linspace(0, 1, a).reshape(shape)
    if b:
        y[-b:] *= (np.linspace(1, 0, b) ** 2).reshape(shape)
    return y


def finish(y, sr, fade_in_s, fade_out_s, peak_db):
    y = fade(y, sr, fade_in_s, fade_out_s)
    peak = np.max(np.abs(y)) or 1.0
    return y * (10 ** (peak_db / 20) / peak)


def write_wav(path, y, sr):
    """16-bit PCM; `y` is (n,) mono or (n, channels)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    channels = 1 if y.ndim == 1 else y.shape[1]
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).round().astype("<i2").tobytes())
    return path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path=CONFIG):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    cfg = load()
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ROOT, cfg["mix"]["out_dir"], "music.wav")
    y = render(cfg)
    write_wav(out, y, cfg["sample_rate"])
    print(json.dumps({"file": os.path.basename(out), "seconds": round(len(y) / cfg["sample_rate"], 3),
                      "peak_dbfs": round(20 * np.log10(np.max(np.abs(y))), 2), "sha256": sha256_file(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
