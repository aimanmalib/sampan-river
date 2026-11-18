"""The vertical short (decision 0008): segments of the 9:16 film joined with crossfades, own captions, same loudness.

Picture: the segments [start, end] (film seconds, config/short.json) are cut from the 9:16 clean master, so the layout and
the end card are the film's own; joins are `xfade` of `crossfade_s`. Sound: the same segments of the film mix joined
with `acrossfade` of the same length (picture and sound stay in step), a fade out at the end, then the film's two-pass
loudnorm. Captions: config/captions.short.en.json in short seconds, drawn with the film's caption style for `source`.
Writes clean-short-9x16.mp4 (no captions, for the caption pixel check) and sampan-river-short-9x16.mp4 to `edit.out_dir`.
Usage: python3 tools/short.py
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import captions, edit  # noqa: E402

SHORT = os.path.join(ROOT, "config", "short.json")


class ShortError(ValueError):
    pass


def total_s(short):
    """Length after the joins: sum of the segments less one crossfade per join."""
    segs, c = short["segments"], float(short["crossfade_s"])
    return round(sum(b - a for a, b in segs) - c * (len(segs) - 1), 3)


def check(short, film):
    """Segments inside the film, in order, each longer than the crossfade; total inside duration_s."""
    end, c = float(film["duration_s"]["target"]), float(short["crossfade_s"])
    last = 0.0
    for a, b in short["segments"]:
        if not last <= a < b <= end:
            raise ShortError(f"segment [{a}, {b}] is outside the film (0..{end}) or out of order")
        if b - a <= 2 * c:
            raise ShortError(f"segment [{a}, {b}] is not longer than two crossfades")
        last = b
    t, d = total_s(short), short["duration_s"]
    if not d["min"] <= t <= d["max"]:
        raise ShortError(f"short runs {t} s, outside {d['min']}..{d['max']} s")
    return t


def check_cues(short, cues):
    t = total_s(short)
    for c in cues:
        if not 0 <= c["start"] < c["end"] <= t:
            raise ShortError(f"cue {c['text']!r} is outside the short (0..{t} s)")
    if min(c["start"] for c in cues) >= short["hook_max_s"]:
        raise ShortError(f"no caption starts in the first {short['hook_max_s']} s")


def short_film(film, short):
    """A copy of film.json in which `version` has the source's size, caption style and band, and the short's length."""
    f, v, src = copy.deepcopy(film), short["version"], short["source"]
    f["output"][v] = f["output"][src]
    for key in ("size", "margin_v", "max_chars_per_line"):
        f["captions"][key][v] = f["captions"][key][src]
    f["measure"]["caption_band"][v] = f["measure"]["caption_band"][src]
    f["duration_s"] = {"min": short["duration_s"]["min"], "max": short["duration_s"]["max"], "target": total_s(short)}
    return f


def offsets(short):
    """Start of each join in the joined stream (xfade / acrossfade offset)."""
    out, t, c = [], 0.0, float(short["crossfade_s"])
    for a, b in short["segments"][:-1]:
        t += b - a - c
        out.append(round(t, 3))
    return out


def video_graph(short, fps):
    c, n = short["crossfade_s"], len(short["segments"])
    parts = [f"[{i}:v]settb=AVTB,fps={fps},format=yuv420p[s{i}]" for i in range(n)]
    prev = "s0"
    for k, off in enumerate(offsets(short), 1):
        out = "out" if k == n - 1 else f"x{k}"
        parts.append(f"[{prev}][s{k}]xfade=transition=fade:duration={c}:offset={off}[{out}]")
        prev = out
    return ";".join(parts)


def audio_graph(short, total):
    c, n, fo = short["crossfade_s"], len(short["segments"]), short["audio_fade_out_s"]
    prev, parts = "0:a", []
    for k in range(1, n):
        out = "j" if k == n - 1 else f"a{k}"
        parts.append(f"[{prev}][{k}:a]acrossfade=d={c}:c1=tri:c2=tri[{out}]")
        prev = out
    parts.append(f"[{prev}]afade=t=out:st={round(total - fo, 3)}:d={fo}[out]")
    return ";".join(parts)


def _inputs(short, path):
    cmd = []
    for a, b in short["segments"]:
        cmd += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", path]
    return cmd


def clean_cmd(short, film, source_clean, out_path):
    c = film["edit"]["clean"]
    return (["ffmpeg", "-y", "-v", "error"] + _inputs(short, source_clean) +
            ["-filter_complex", video_graph(short, film["edit"]["fps"]), "-map", "[out]", "-an", "-c:v", "libx264",
             "-crf", str(c["crf"]), "-preset", c["preset"], "-pix_fmt", "yuv420p", out_path])


def mix_cmd(short, film, source_mix, out_path):
    return (["ffmpeg", "-y", "-v", "error"] + _inputs(short, source_mix) +
            ["-filter_complex", audio_graph(short, total_s(short)), "-map", "[out]",
             "-ar", str(film["audio"]["sample_rate"]), "-c:a", "pcm_s16le", out_path])


def main(argv):
    if argv:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    film, short = captions.load(captions.FILM), captions.load(SHORT)
    cues = captions.load(os.path.join(ROOT, short["captions"]))["cues"]
    check(short, film)
    check_cues(short, cues)
    sf, v, src = short_film(film, short), short["version"], short["source"]
    out_dir = os.path.join(ROOT, film["edit"]["out_dir"])
    source_clean = os.path.join(out_dir, f"clean-{src}.mp4")
    source_mix = os.path.join(ROOT, film["edit"]["mix"].format(orientation=film["edit"]["orientation"][src]))
    for p in (source_clean, source_mix):
        if not os.path.exists(p):
            raise ShortError(f"{p} missing: run tools/mix.py and tools/edit.py {src} first")
    ass = os.path.join(out_dir, f"captions-{v}.ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write(captions.captions_ass(cues, sf, v))
    clean = os.path.join(out_dir, f"clean-{v}.mp4")
    edit.run(clean_cmd(short, sf, source_clean, clean), out_dir)
    mix_path = os.path.join(out_dir, f"mix-{v}.wav")
    edit.run(mix_cmd(short, sf, source_mix, mix_path), out_dir)
    probe = edit.run(["ffmpeg", "-hide_banner", "-i", mix_path, "-af",
                      f"loudnorm={edit.loudnorm_target(sf)}:print_format=json", "-f", "null", "-"], out_dir)
    measured = edit.parse_loudnorm(probe.stderr)
    final = os.path.join(out_dir, f"sampan-river-{v}.mp4")
    edit.run(edit.final_cmd(sf, clean, mix_path, os.path.basename(ass), edit.second_pass(sf, measured), final), out_dir)
    print(json.dumps({"clean": os.path.relpath(clean, ROOT), "final": os.path.relpath(final, ROOT),
                      "duration_s": total_s(short), "loudnorm_pass1": measured}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
