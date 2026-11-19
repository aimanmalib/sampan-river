"""Narration placed over the music bed with a deterministic duck (decision 0012).

1. Place: each cue's take starts speaking at cue start + lead_s. Its window runs to the next cue's start - min_gap_s
   (the last cue: the end of the version). A take longer than its window is sped up with ffmpeg `atempo` up to
   max_tempo; longer than that, the line is held back (`ok: false`) and the rest still speak.
2. Retime: caption times follow the voice: start = voice start - lead_s, end = voice end + tail_s, at least min_cue_s,
   never past the next cue's start. Burned captions, bands and the SRT read the same times.
3. Mix: each line is set to voice_rms_dbfs; the bed (music + ambience, tools/mix.py) is multiplied by a gain envelope
   that is -duck_db inside every voice span with linear ramps of ramp_s outside it, and 1 elsewhere; the sum goes
   through the mix limiter. ffmpeg `sidechaincompress` was not used: its attack and release follow the signal, while
   here every span is known, so the envelope is exact and testable.
4. Stats (MEASURED "Narration mix"): voice_rms_db and bed_under_voice_db inside the spans, gap_db = their difference,
   bed_outside_change_db = level change of the bed further than ramp_s from any span (must stay about 0).
Usage: python3 tools/narrate.py <16x9|9x16|short-9x16> [--retime] [--write]
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import captions, ledger, mix, short, voice  # noqa: E402

MEASURED = os.path.join(ROOT, "docs", "MEASURED.md")
MIX_COLUMNS = ("version", "voice_rms_db", "bed_under_voice_db", "gap_db", "bed_outside_change_db")


def place(cues, takes, cfg, end_s):
    """cues sorted by start; takes = {id: (voice_from_s, voice_to_s)} inside each take file.
    Returns [{id, at, tempo, offset, voice_s, window_s, ok}]: `at` = film second the voice starts,
    `offset` = seconds into the (tempo-changed) take where the voice starts."""
    cues = sorted(cues, key=lambda c: c["start"])
    out = []
    for i, c in enumerate(cues):
        if c["id"] not in takes:
            out.append({"id": c["id"], "ok": False, "reason": "no take"})
            continue
        a, b = takes[c["id"]]
        at = float(c["start"]) + cfg["lead_s"]
        limit = (float(cues[i + 1]["start"]) if i + 1 < len(cues) else float(end_s)) - cfg["min_gap_s"]
        window, length = limit - at, b - a
        tempo = 1.0 if length <= window else float(np.ceil(length / window * 1000) / 1000)
        ok = tempo <= cfg["max_tempo"]
        out.append({"id": c["id"], "at": round(at, 3), "tempo": tempo, "offset": round(a / tempo, 3),
                    "voice_s": round(length / tempo, 3), "window_s": round(window, 3), "ok": ok,
                    "reason": None if ok else f"needs tempo {tempo} > {cfg['max_tempo']}"})
    return out


def retime(cues, placed, cfg):
    """New cue list with times from the placed voice; cues whose line is held back keep their times."""
    by_id = {p["id"]: p for p in placed if p["ok"]}
    cues = sorted((dict(c) for c in cues), key=lambda c: c["start"])
    for c in cues:
        p = by_id.get(c["id"])
        if p:
            c["start"] = round(max(0.0, p["at"] - cfg["lead_s"]), 2)
            least = max(cfg["min_cue_s"], len(c["text"]) / cfg["srt"]["max_cps"])  # readable at max_cps
            c["end"] = round(max(p["at"] + p["voice_s"] + cfg["tail_s"], c["start"] + least), 2)
    for c, nxt in zip(cues, cues[1:]):
        c["end"] = min(c["end"], nxt["start"])
    return cues


def spans(placed):
    return [(p["at"], p["at"] + p["voice_s"]) for p in placed if p["ok"]]


def envelope(n, sr, voice_spans, duck_db, ramp_s):
    """Gain per sample: 10^(-duck_db/20) inside each span, linear ramps of ramp_s on both sides, 1 elsewhere."""
    t = np.arange(n) / sr
    low = 10 ** (-duck_db / 20)
    gain = np.ones(n)
    for a, b in voice_spans:
        dist = np.maximum(np.maximum(a - t, t - b), 0.0)  # seconds outside the span, 0 inside
        g = low + (1 - low) * np.clip(dist / ramp_s, 0.0, 1.0) if ramp_s > 0 else np.where(dist > 0, 1.0, low)
        gain = np.minimum(gain, g)
    return gain


def voice_track(n, sr, lines, rms_dbfs):
    """lines = [(film second the array starts, mono array)] -> mono track with each line at rms_dbfs."""
    y = np.zeros(n)
    for start, arr in lines:
        i = int(round(start * sr))
        arr = mix.to_level(np.asarray(arr, dtype=np.float64), rms_dbfs)
        k = min(len(arr), n - i)
        if k > 0 and i >= 0:
            y[i:i + k] += arr[:k]
    return y


def narrate(bed, voice_mono, gain, peak_db, sr, block_s):
    """(n, 2) bed * gain + voice in both channels, through the mix limiter."""
    return mix.limit(bed * gain[:, None] + voice_mono[:, None], peak_db, sr, block_s)


def _mask(n, sr, voice_spans, pad_s):
    t = np.arange(n) / sr
    m = np.zeros(n, dtype=bool)
    for a, b in voice_spans:
        m |= (t >= a - pad_s) & (t <= b + pad_s)
    return m


def mix_stats(bed, voice_mono, gain, voice_spans, sr, ramp_s):
    inside, near = _mask(len(bed), sr, voice_spans, 0.0), _mask(len(bed), sr, voice_spans, ramp_s)
    ducked = bed * gain[:, None]
    v, under = mix.rms_db(voice_mono[inside]), mix.rms_db(ducked[inside])
    outside = mix.rms_db(ducked[~near]) - mix.rms_db(bed[~near]) if (~near).any() else 0.0
    return {"voice_rms_db": round(v, 2), "bed_under_voice_db": round(under, 2), "gap_db": round(v - under, 2),
            "bed_outside_change_db": round(outside, 2)}


def mix_row(version, stats):
    return "| " + " | ".join(str(x) for x in [version] + [stats[k] for k in MIX_COLUMNS[1:]]) + " |"


def upsert_mix(md, version, stats):
    """Insert or replace the version's row in the "Narration mix" table of MEASURED.md."""
    head = "| " + " | ".join(MIX_COLUMNS) + " |"
    if head not in md:
        md = md.rstrip("\n") + "\n\n## Narration mix\n\n" + head + "\n|" + "---|" * len(MIX_COLUMNS) + "\n"
    lines = md.split("\n")
    at = lines.index(head) + 2
    while at < len(lines) and lines[at].startswith("|") and not lines[at].startswith(f"| {version} |"):
        at += 1
    if at < len(lines) and lines[at].startswith(f"| {version} |"):
        lines[at] = mix_row(version, stats)
    else:
        lines.insert(at, mix_row(version, stats))
    return "\n".join(lines)


def atempo_filter(tempo):
    return f"atempo={tempo}" if tempo != 1.0 else "anull"


def decode_take(path, tempo, sr):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", atempo_filter(tempo), "-f", "f32le", "-ac", "1",
                          "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def chosen_takes(cues, cfg, voice_id):
    """{id: (mp3 path, alignment span)} for every cue with a passing take in the ledger and the cache."""
    rows, out = voice.read_ledger(os.path.join(ROOT, cfg["ledger"])), {}
    for c in cues:
        h = voice.text_hash(voice.say(c, cfg), cfg, voice_id)
        row = voice.passing_take(rows, c["id"], h, cfg)
        if row:
            base = voice.take_path(os.path.join(ROOT, cfg["cache_dir"]), c["id"], h, row["take"], "json")
            with open(base, encoding="utf-8") as f:
                out[c["id"]] = (base[:-4] + "mp3", voice.span(json.load(f)["alignment"]))
    return out


def sources(version, film):
    """(captions file, bed wav, end second) of a version: the short narrates its own cut bed (decision 0012)."""
    sh = captions.load(short.SHORT)
    if version == sh["version"]:
        return (os.path.join(ROOT, sh["captions"]), os.path.join(ROOT, film["edit"]["out_dir"], f"mix-{version}.wav"),
                short.total_s(sh))
    bed = os.path.join(ROOT, film["edit"]["mix"].format(orientation=film["edit"]["orientation"][version]))
    return captions.CAPTIONS, bed, float(film["duration_s"]["target"])


def main(argv):
    film, cfg = captions.load(captions.FILM), ledger.load_json(voice.CONFIG)
    if not argv or not re.fullmatch(r"16x9|9x16|short-9x16", argv[0]):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    version, voice_id = argv[0], os.environ.get(cfg["voice_env"])
    if not voice_id:
        print(f"set {cfg['voice_env']} in the environment (it names the cached takes)", file=sys.stderr)
        return 2
    cap_path, bed_path, end_s = sources(version, film)
    doc = captions.load(cap_path)
    takes = chosen_takes(doc["cues"], cfg, voice_id)
    placed = place(doc["cues"], {k: v[1] for k, v in takes.items()}, cfg, end_s)
    sr, music_cfg = cfg["sample_rate"], ledger.load_json(mix.music.CONFIG)
    bed = mix.decode(bed_path, 0, end_s, sr)
    lines = []
    pad = cfg["lead_s"]  # keep breath edges; the level is set on the voiced part only
    for p in placed:
        if p["ok"]:
            arr = decode_take(takes[p["id"]][0], p["tempo"], sr)
            lo = max(0.0, p["offset"] - pad)
            arr = arr[int(lo * sr):int((p["offset"] + p["voice_s"] + pad) * sr)]
            lines.append((p["at"] - (p["offset"] - lo), arr))
    vt = voice_track(len(bed), sr, lines, cfg["voice_rms_dbfs"])
    sp = spans(placed)
    gain = envelope(len(bed), sr, sp, cfg["duck_db"], cfg["ramp_s"])
    y = narrate(bed, vt, gain, music_cfg["synth"]["peak_db"], sr, music_cfg["mix"]["limiter_block_s"])
    out = os.path.join(ROOT, cfg["cache_dir"], f"narrated-{version}.wav")
    mix.music.write_wav(out, y, sr)
    stats = mix_stats(bed, vt, gain, sp, sr, cfg["ramp_s"])
    print(json.dumps({"version": version, "placed": placed, "mix": stats, "wav": os.path.relpath(out, ROOT)}))
    if "--retime" in argv:
        doc["cues"] = retime(doc["cues"], placed, cfg)
        with open(cap_path, "w", encoding="utf-8") as f:
            f.write(captions.dump_cues(doc))
    if "--write" in argv:
        with open(MEASURED, encoding="utf-8") as f:
            md = f.read()
        with open(MEASURED, "w", encoding="utf-8") as f:
            f.write(upsert_mix(md, f"preview-{version}", stats))
    return 1 if any(not p["ok"] for p in placed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
