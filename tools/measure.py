"""Measure a final film against the limits in config/film.json and write the result to docs/MEASURED.md.

Checks: size, frame rate, duration (min..max), audio stream present with the same duration (+-0.1 s), integrated
loudness and true peak (ffmpeg ebur128), no silence longer than `audio.silence_max_s` in the first
`audio.silence_check_s` seconds, zero words from the local speech check (tools/transcribe.py), and the caption pixel
check (decision 0005): at each cue middle the caption band of the final file differs from the clean master, and at each
gap between cues it does not. One frame per cue goes to `measure.frames_dir` for a person to read.
The vertical short (`short-9x16`, decision 0008) is measured the same way against config/short.json (tools/short.py).
Narrated versions (decision 0012, `audio.speech_check.expect` = script) must instead be heard saying the script:
`speech_match` >= match_min. `<version><silent_suffix>` is the same picture without the voice: checked as silent, no frames.
Usage: python3 tools/measure.py <16x9|9x16|short-9x16>[<silent_suffix>] [--write]
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
from tools import captions, short, transcribe, ve, voice  # noqa: E402

MEASURED = os.path.join(ROOT, "docs", "MEASURED.md")
COLUMNS = ("version", "width", "height", "duration_s", "audio", "lufs_i", "true_peak_db", "whisper_words",
           "speech_match", "caption_cues", "sha256")


def probe(path):
    p = ve.ffprobe(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    out = {"width": v["width"], "height": v["height"], "fps": round(num / den, 3), "video_codec": v["codec_name"],
           "profile": v.get("profile"), "pix_fmt": v.get("pix_fmt"), "duration_s": round(float(p["format"]["duration"]), 3),
           "video_s": round(float(v.get("duration", p["format"]["duration"])), 3), "audio": a is not None}
    if a:
        out.update(audio_codec=a["codec_name"], sample_rate=int(a["sample_rate"]), channels=a["channels"],
                   audio_s=round(float(a.get("duration", 0)), 3))
    return out


def parse_ebur128(stderr):
    """Integrated loudness and true peak from the ebur128 summary."""
    summary = stderr[stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    tp = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not (i and tp):
        raise ValueError("no ebur128 summary")
    return float(i.group(1)), float(tp.group(1))


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    return parse_ebur128(r.stderr)


def parse_silences(stderr, upto_s):
    """[(start, end)] from silencedetect; an open silence at the end runs to `upto_s`."""
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", stderr)]
    return [(s, ends[i] if i < len(ends) else upto_s) for i, s in enumerate(starts)]


def silences(path, upto_s, noise_db, min_s):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-t", str(upto_s), "-i", path, "-map", "0:a", "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_s}", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    return parse_silences(r.stderr, upto_s)


def luma(path, t, width, height):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8)[:width * height].reshape(height, width).astype(np.int16)


def band_diff(a, b, band):
    """Mean absolute difference inside rows band[0]..band[1] (fractions of the height)."""
    h = a.shape[0]
    r0, r1 = int(band[0] * h), int(band[1] * h)
    return float(np.mean(np.abs(a[r0:r1] - b[r0:r1])))


def sample_times(cues, film_end, min_gap):
    """(kind, index, t): the middle of every cue and of every gap of at least `min_gap` seconds between cues."""
    cues = sorted(cues, key=lambda c: c["start"])
    out = [("cue", i, round((c["start"] + c["end"]) / 2, 3)) for i, c in enumerate(cues)]
    edges = [0.0] + [x for c in cues for x in (c["start"], c["end"])] + [film_end]
    for g, (a, b) in enumerate(zip(edges[::2], edges[1::2])):
        if b - a >= min_gap:
            out.append(("gap", g, round((a + b) / 2, 3)))
    return out


def caption_check(clean, final, cues, film, version, diff=None):
    """[{kind, index, t, diff, ok}] per sample time; `diff(t)` is injectable for tests."""
    m, o = film["measure"], film["output"][version]
    band = m["caption_band"][version]
    if diff is None:
        def diff(t):
            return band_diff(luma(clean, t, o["width"], o["height"]), luma(final, t, o["width"], o["height"]), band)
    rows = []
    for kind, i, t in sample_times(cues, float(film["duration_s"]["target"]), m["min_gap_s"]):
        d = round(diff(t), 2)
        ok = d > m["in_cue_min"] if kind == "cue" else d < m["out_cue_max"]
        rows.append({"kind": kind, "index": i, "t": t, "diff": d, "ok": ok})
    return rows


def save_frames(final, cues, film, version):
    m = film["measure"]
    out = []
    for i, c in enumerate(sorted(cues, key=lambda c: c["start"]), 1):
        path = os.path.join(ROOT, m["frames_dir"], f"{version}-cue-{i:02d}.jpg")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{(c['start'] + c['end']) / 2:.3f}", "-i", final,
                        "-frames:v", "1", "-vf", f"scale={m['frame_width']}:-2:flags=lanczos", "-q:v",
                        str(m["frame_quality"]), path], check=True)
        size = os.path.getsize(path)
        if size > m["frame_max_bytes"]:
            raise ValueError(f"{path}: {size} bytes over {m['frame_max_bytes']}")
        out.append(os.path.relpath(path, ROOT))
    return out


def split_version(version, film):
    """(picture version, narrated?) e.g. '16x9-tanpa-suara' -> ('16x9', False)."""
    sc = film["audio"]["speech_check"]
    suffix = sc.get("silent_suffix")
    if suffix and version.endswith(suffix):
        return version[:-len(suffix)], False
    return version, sc.get("expect") == "script"


def script_text(cues, voice_cfg):
    return " ".join(voice.say(c, voice_cfg) for c in sorted(cues, key=lambda c: c["start"]))


def verdict(result, film):
    """Names of failed limits; empty = pass."""
    base, narrated = split_version(result["version"], film)
    d, a, o = film["duration_s"], film["audio"], film["output"][base]
    p, fails = result["probe"], []
    if (p["width"], p["height"]) != (o["width"], o["height"]):
        fails.append("size")
    if p["fps"] != film["edit"]["fps"]:
        fails.append("fps")
    if not d["min"] <= p["duration_s"] <= d["max"]:
        fails.append("duration")
    if not p["audio"] or abs(p["audio_s"] - p["video_s"]) > 0.1:
        fails.append("audio")
    if abs(result["lufs_i"] - a["lufs_target"]) > a["lufs_tolerance"]:
        fails.append("lufs")
    if result["true_peak_db"] > a["true_peak_max_db"]:
        fails.append("true_peak")
    if any(e - s > a["silence_max_s"] for s, e in result["silences"]):
        fails.append("silence")
    if narrated:
        if result.get("speech_match") is None or result["speech_match"] < a["speech_check"]["match_min"]:
            fails.append("speech_match")
    elif result["whisper_words"] > a["speech_check"]["max_words"]:
        fails.append("speech")
    if not all(r["ok"] for r in result["captions"]):
        fails.append("captions")
    return fails


def table_row(result):
    p, cues = result["probe"], [r for r in result["captions"] if r["kind"] == "cue"]
    vals = (result["version"], p["width"], p["height"], p["duration_s"], "yes" if p["audio"] else "no", result["lufs_i"],
            result["true_peak_db"], result["whisper_words"],
            "-" if result.get("speech_match") is None else result["speech_match"], f"{sum(r['ok'] for r in cues)}/{len(cues)}", result["sha256"])
    return "| " + " | ".join(str(v) for v in vals) + " |"


def upsert(md, result):
    """Insert or replace the version's row in the Final films table and its detail block."""
    head = "| " + " | ".join(COLUMNS) + " |"
    md = migrate(md)
    if head not in md:
        md = md.rstrip("\n") + "\n\n## Final films\n\n" + head + "\n|" + "---|" * len(COLUMNS) + "\n"
    lines = md.split("\n")
    row = table_row(result)
    idx = [i for i, ln in enumerate(lines) if ln.startswith(f"| {result['version']} |")]
    if idx:
        lines[idx[0]] = row
    else:
        at = lines.index(head) + 2
        while at < len(lines) and lines[at].startswith("|"):
            at += 1
        lines.insert(at, row)
    md = "\n".join(lines)
    start, end = f"<!-- detail:{result['version']} -->", f"<!-- /detail:{result['version']} -->"
    block = f"{start}\n{detail(result)}\n{end}"
    if start in md:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block, md, flags=re.S)
    return md.rstrip("\n") + "\n\n" + block + "\n"


def migrate(md):
    """Add the speech_match column ("-" = silent version) to a table written before decision 0012."""
    old = [c for c in COLUMNS if c != "speech_match"]
    at = COLUMNS.index("speech_match")
    out, inside = [], False
    for ln in md.split("\n"):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.startswith("|") else None
        if cells == old:
            inside = True
        elif not ln.startswith("|"):
            inside = False
        if inside and cells and len(cells) == len(old):
            cells.insert(at, "speech_match" if cells == old else ("---" if set(cells[0]) == {"-"} else "-"))
            ln = "| " + " | ".join(cells) + " |" if cells[0] != "---" else "|" + "---|" * len(cells)
        out.append(ln)
    return "\n".join(out)


def detail(result):
    p = result["probe"]
    out = [f"### {result['version']} detail", "",
           f"Video {p['video_codec']} {p['profile']} {p['pix_fmt']} {p['fps']} fps, {p['video_s']} s; audio "
           f"{p.get('audio_codec')} {p.get('sample_rate')} Hz {p.get('channels')} ch, {p.get('audio_s')} s. "
           f"Silences over the limit in the opening seconds: {len(result['silences'])}. Failed limits: "
           f"{', '.join(result['fails']) or 'none'}." + (f" Heard: \"{result['heard']}\"; speech match "
                                                         f"{result['speech_match']}." if result.get("heard") else ""), "",
           "| sample | t (s) | caption band diff | pass |", "|---|---|---|---|"]
    out += [f"| {r['kind']} {r['index'] + 1} | {r['t']} | {r['diff']} | {'yes' if r['ok'] else 'no'} |"
            for r in result["captions"]]
    return "\n".join(out)


def measure(version, film, cues):
    out_dir = os.path.join(ROOT, film["edit"]["out_dir"])
    base, narrated = split_version(version, film)
    final, clean = os.path.join(out_dir, f"sampan-river-{version}.mp4"), os.path.join(out_dir, f"clean-{base}.mp4")
    a = film["audio"]
    lufs_i, tp = loudness(final)
    heard = transcribe.check(final, a["speech_check"])
    match = transcribe.speech_match(heard["text"], script_text(cues, captions.load(voice.CONFIG))) if narrated else None
    result = {"version": version, "probe": probe(final), "lufs_i": lufs_i, "true_peak_db": tp,
              "silences": silences(final, a["silence_check_s"], film["measure"]["silence_noise_db"], a["silence_max_s"]),
              "whisper_words": heard["words"], "speech_match": match, "heard": heard["text"] if narrated else "",
              "captions": caption_check(clean, final, cues, film, base),
              "frames": save_frames(final, cues, film, base) if base == version else [],
              "sha256": ve.sha256_file(final)}
    result["fails"] = verdict(result, film)
    return result


def main(argv):
    film, sh = captions.load(captions.FILM), captions.load(short.SHORT)
    base = split_version(argv[0], film)[0] if argv else None
    if base not in ("16x9", "9x16", sh["version"]):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    cues = captions.load(captions.CAPTIONS)["cues"]
    if base == sh["version"]:
        film, cues = short.short_film(film, sh), captions.load(os.path.join(ROOT, sh["captions"]))["cues"]
    result = measure(argv[0], film, cues)
    print(json.dumps(result))
    if "--write" in argv:
        with open(MEASURED, encoding="utf-8") as f:
            md = f.read()
        with open(MEASURED, "w", encoding="utf-8") as f:
            f.write(upsert(md, result))
    return 1 if result["fails"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
