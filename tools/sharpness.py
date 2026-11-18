"""Sharpness of the 9:16 layouts (decision 0007): how sharp the picture looks on the phone screen in each layout.

For each shot of the 9:16 version, at `measure.sharpness.sample_fracs` of its window, the same scene region (a
`region_aspect` box at full source height, centred where the `crop_fill` box is centred at that moment) is cut from the
accepted clip and scaled with the output scaler to the size it is shown at in each layout: `blur_fill` (full source
width at output width) and `crop_fill` for every aspect in `aspects`. Sharpness = variance of the 4-neighbour Laplacian
of the luma. A layout passes when its mean ratio to `blur_fill` over all samples is at least `min_ratio`; the choice is
the passing aspect with the largest picture. Same region in every layout, so the ratio measures scaling, not content.
Usage: python3 tools/sharpness.py [--write]   (prints JSON; --write puts the table in docs/MEASURED.md)
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
from tools import captions, layout, mix  # noqa: E402

MEASURED = os.path.join(ROOT, "docs", "MEASURED.md")
VERSION = "9x16"


def laplacian_var(a):
    a = a.astype(np.float64)
    lap = a[1:-1, :-2] + a[1:-1, 2:] + a[:-2, 1:-1] + a[2:, 1:-1] - 4 * a[1:-1, 1:-1]
    return float(lap.var())


def display_widths(film):
    """{layout name: shown width of one source pixel column, in output pixels}."""
    cfg, out_w = film["measure"]["sharpness"], film["output"][VERSION]["width"]
    sw, _ = layout.source_size(film, VERSION)
    widths = {"blur_fill": out_w / sw}
    for name, aspect in cfg["aspects"].items():
        widths[name] = out_w / layout.crop_size(film, VERSION, aspect)[0]
    return widths


def region_luma(path, t, left, rw, rh, scale, flags):
    w, h = int(round(rw * scale / 2)) * 2, int(round(rh * scale / 2)) * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf",
                          f"crop={rw}:{rh}:{left}:0,scale={w}:{h}:flags={flags},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8)[:w * h].reshape(h, w)


def samples(film, shots_cfg):
    """[(clip, t_in_clip, t_in_window, left_px)] for the region box."""
    cfg = film["measure"]["sharpness"]
    out = []
    for clip, (w0, w1), _ in mix.segments(shots_cfg, film["edit"]["orientation"][VERSION]):
        keys = layout.keyframes(film, VERSION, clip, cfg["region_aspect"])
        for frac in cfg["sample_fracs"]:
            rel = round((w1 - w0) * frac, 3)
            out.append((clip, round(w0 + rel, 3), rel, int(round(layout.left_at(keys, rel)))))
    return out


def summarise(rows, film):
    """Mean ratio of each crop aspect to blur_fill, pass flags and the chosen layout (None = keep blur_fill)."""
    cfg = film["measure"]["sharpness"]
    ratios, chosen = {}, None
    for name in cfg["aspects"]:
        ratios[name] = round(float(np.mean([r[name] / r["blur_fill"] for r in rows])), 3)
    passing = [n for n in cfg["aspects"] if ratios[n] >= cfg["min_ratio"]]
    if passing:
        chosen = max(passing, key=lambda n: layout.picture_box(film, VERSION, "crop_fill", cfg["aspects"][n])[3])
    return {"ratios": ratios, "passing": passing, "chosen": chosen, "min_ratio": cfg["min_ratio"]}


def measure(film, shots_cfg, clips_dir, luma=region_luma):
    cfg, o = film["measure"]["sharpness"], film["output"][VERSION]
    _, sh = layout.source_size(film, VERSION)
    rw, _ = layout.crop_size(film, VERSION, cfg["region_aspect"])
    widths, rows = display_widths(film), []
    for clip, t, rel, left in samples(film, shots_cfg):
        row = {"clip": clip, "t": t, "window_t": rel, "left": left}
        for name, scale in widths.items():
            row[name] = round(laplacian_var(luma(os.path.join(clips_dir, clip), t, left, rw, sh, scale, o["scale"])), 1)
        rows.append(row)
    return {"rows": rows, **summarise(rows, film)}


def table(result, film):
    names = ["blur_fill"] + list(film["measure"]["sharpness"]["aspects"])
    out = ["<!-- sharpness -->", "## Sharpness (9:16 layouts)", "",
           "Variance of the Laplacian of the luma, same scene region shown at each layout's size (tools/sharpness.py).",
           "", "| clip | t (s) | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    out += [f"| {r['clip']} | {r['t']} | " + " | ".join(str(r[n]) for n in names) + " |" for r in result["rows"]]
    ratio = ", ".join(f"{n} {v}" for n, v in result["ratios"].items())
    out += ["", f"Mean ratio to blur_fill: {ratio}. Limit: {result['min_ratio']}. "
                f"Chosen: {result['chosen'] or 'blur_fill (no crop passes)'}.", "<!-- /sharpness -->"]
    return "\n".join(out)


def upsert(md, block):
    if "<!-- sharpness -->" in md:
        return re.sub(r"<!-- sharpness -->.*?<!-- /sharpness -->", lambda _: block, md, flags=re.S)
    return md.rstrip("\n") + "\n\n" + block + "\n"


def main(argv):
    film = captions.load(captions.FILM)
    clips_dir = os.path.join(ROOT, captions.load(mix.music.CONFIG)["mix"]["clips_dir"])
    result = measure(film, captions.load(mix.SHOTS), clips_dir)
    print(json.dumps(result))
    if "--write" in argv:
        with open(MEASURED, encoding="utf-8") as f:
            md = f.read()
        with open(MEASURED, "w", encoding="utf-8") as f:
            f.write(upsert(md, table(result, film)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
