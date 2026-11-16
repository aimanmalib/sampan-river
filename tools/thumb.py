"""Thumbnail (M6): one frame of an accepted clip, scaled with lanczos, with the title drawn by code.

Everything comes from config/film.json `thumbnail`: the shot and the clip second (it must sit inside the shot's edit
window, so the still is a frame of the film), the output size, the text lines, font, sizes, colours and margins.
The text is an ASS file rendered by ffmpeg's `ass` filter, top-right aligned, so no image model draws letters.
Usage: python3 tools/thumb.py   (writes the ASS next to `thumbnail.out` and the JPEG at `thumbnail.out`)
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import captions, mix  # noqa: E402

SHOTS = os.path.join(ROOT, "config", "shots.json")


class ThumbError(ValueError):
    pass


def source(thumb, shots_cfg):
    """(clip file name, clip second) for the thumbnail, refused when the second is outside the edit window."""
    shot = next((s for s in shots_cfg["shots"] if s["id"] == thumb["shot"]), None)
    if shot is None:
        raise ThumbError(f"thumbnail shot {thumb['shot']!r} is not in config/shots.json")
    clip = shot.get("accepted", {}).get(thumb["orientation"])
    if not clip:
        raise ThumbError(f"shot {shot['id']} has no accepted {thumb['orientation']} clip")
    t, (w0, w1) = float(thumb["clip_s"]), shot["window_s"]
    if not w0 <= t <= w1:
        raise ThumbError(f"clip_s {t} is outside the edit window {w0} to {w1} s of {shot['id']}")
    return clip, t


def thumb_ass(thumb):
    """ASS with the first line large and the rest smaller, right-aligned from the top-right margin."""
    w, h = thumb["width"], thumb["height"]
    big, small = thumb["size"]
    styles = [captions._style(n, thumb["font"], s, thumb["colour"], thumb["outline_colour"], True,
                              thumb["outline_px"], 0, 9, 0, 0)
              for n, s in (("ThumbTitle", big), ("ThumbLine", small))]
    x, y = w - int(thumb["margin_right_px"]), int(thumb["margin_top_px"])
    events = []
    for i, line in enumerate(thumb["lines"]):
        name = "ThumbTitle" if i == 0 else "ThumbLine"
        events.append(f"Dialogue: 0,0:00:00.00,0:00:10.00,{name},,0,0,0,,{{\\pos({x},{y})}}{line}\n")
        y += (big if i == 0 else small) + int(thumb["line_gap_px"])
    if y > h:
        raise ThumbError(f"thumbnail text runs to y={y}, below the frame height {h}")
    return captions._header(w, h, styles) + "".join(events)


def thumb_cmd(thumb, clip_path, t, ass_name, out_path):
    vf = f"scale={thumb['width']}:{thumb['height']}:flags={thumb['scale']},ass={ass_name}"
    return ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", clip_path, "-frames:v", "1", "-vf", vf,
            "-q:v", str(thumb["jpeg_qscale"]), out_path]


def main(argv=None):
    film = captions.load(captions.FILM)
    thumb = film["thumbnail"]
    clip, t = source(thumb, captions.load(SHOTS))
    out = os.path.join(ROOT, thumb["out"])
    out_dir = os.path.dirname(out)
    os.makedirs(out_dir, exist_ok=True)
    ass = os.path.join(out_dir, "thumb.ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write(thumb_ass(thumb))
    clips_dir = os.path.join(ROOT, captions.load(mix.music.CONFIG)["mix"]["clips_dir"])
    subprocess.run(thumb_cmd(thumb, os.path.join(clips_dir, clip), t, os.path.basename(ass), out),
                   cwd=out_dir, check=True)
    size = os.path.getsize(out)
    if size > int(thumb["max_bytes"]):
        raise ThumbError(f"{out} is {size} bytes, over max_bytes {thumb['max_bytes']}")
    with open(out, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(json.dumps({"thumbnail": os.path.relpath(out, ROOT), "clip": clip, "clip_s": t, "bytes": size,
                      "sha256": sha}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
