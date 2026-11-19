"""Vertical share image (decision 0014): one committed 9:16 cue frame recomposed to 4:5 for link previews.

Everything comes from config/site.json `og_build`: the frame, the picture crop, the layout and the output paths.
The picture is a lanczos crop of the frame placed on a blurred copy of the same frame; the text is the film's own
words (title from config/film.json, hook = a caption id from config/captions.en.json, figure and label = the 9:16
band carrying `figure_fact` in config/bands.json), drawn by ffmpeg's `ass` filter. No image model is involved.
Usage: python3 tools/og.py [--crops]   (--crops also writes the centre 1:1 and 1.91:1 crops a preview may show)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import captions  # noqa: E402


class OgError(ValueError):
    pass


def load(root, name):
    with open(os.path.join(root, "config", name), encoding="utf-8") as f:
        return json.load(f)


def words(og, film, caps, bands, domain):
    """{'title', 'hook' (list of lines), 'figure', 'label', 'domain'}: all of it already in the film or the config."""
    cue = next((c for c in caps["cues"] if c["id"] == og["hook_caption"]), None)
    if cue is None:
        raise OgError(f"hook caption {og['hook_caption']!r} is not in config/captions.en.json")
    band = next((b for b in bands["9x16"] if b.get("fact") == og["figure_fact"]), None)
    if band is None:
        raise OgError(f"no 9:16 band carries fact {og['figure_fact']!r}")
    return {"title": film["title"], "hook": textwrap.wrap(cue["text"], og["hook_wrap_chars"]),
            "figure": band["figure"], "label": band["label"], "domain": domain}


def centre_box(og, height):
    """(top, bottom) of a full-width centre crop of the given height."""
    top = (og["height"] - height) // 2
    return top, top + height


def check_layout(og, text):
    """Problems with the layout: the hook, the picture and the figure must sit where each preview crop keeps them."""
    problems = []
    t191, b191 = centre_box(og, og["crops"]["191"]["height"])
    t11, b11 = centre_box(og, og["crops"]["1x1"]["height"])
    hook_bottom = og["hook"]["y"] + og["hook"]["line_px"] * len(text["hook"])
    pic_top, pic_bottom = og["picture"]["y"], og["picture"]["y"] + og["picture"]["height"]
    if og["hook"]["y"] < t191 or hook_bottom > pic_top:
        problems.append("hook caption is not inside the 1.91:1 box above the picture")
    if pic_top < t191 or pic_bottom > b191:
        problems.append("picture is not inside the 1.91:1 box")
    if og["title"]["y"] < t11 or og["title"]["y"] + og["title"]["size"] > og["hook"]["y"]:
        problems.append("title is not inside the 1:1 box above the hook")
    if og["figure"]["y"] < pic_bottom or og["label"]["y"] + og["label"]["size"] > b11:
        problems.append("figure is not inside the 1:1 box below the picture")
    if og["domain"]["y"] + og["domain"]["size"] > og["height"]:
        problems.append("domain runs off the image")
    if picture_width(og) > og["width"]:
        problems.append("picture is wider than the image")
    return problems


def picture_width(og):
    _, _, cw, ch = og["picture_crop"]
    return round(og["picture"]["height"] * cw / ch / 2) * 2


def og_ass(og, text, cap_style):
    """ASS with every line centred at x = width/2, its top at the configured y."""
    font, col, out = cap_style["font"], cap_style["primary_colour"], cap_style["outline_colour"]
    lines = [("Title", og["title"], text["title"]), ("Figure", og["figure"], text["figure"]),
             ("Label", og["label"], text["label"]), ("Domain", og["domain"], text["domain"])]
    lines += [("Hook", dict(og["hook"], y=og["hook"]["y"] + i * og["hook"]["line_px"]), line)
              for i, line in enumerate(text["hook"])]
    styles, seen, events = [], set(), []
    x = og["width"] // 2
    for name, spec, line in lines:
        if name not in seen:
            seen.add(name)
            styles.append(captions._style(name, font, spec["size"], col, out, True, og["outline_px"], 0, 8, 0, 0))
        events.append(f"Dialogue: 0,0:00:00.00,0:00:10.00,{name},,0,0,0,,{{\\pos({x},{spec['y']})}}{line}\n")
    return captions._header(og["width"], og["height"], styles) + "".join(events)


def og_cmd(og, frame_path, ass_name, out_path):
    w, h, s = og["width"], og["height"], og["scale"]
    cx, cy, cw, ch = og["picture_crop"]
    pw = picture_width(og)
    graph = (f"[0:v]split[a][b];"
             f"[a]scale={w}:{h}:force_original_aspect_ratio=increase:flags={s},crop={w}:{h},"
             f"boxblur={og['background_blur']}:2,eq=brightness={og['background_brightness']}[bg];"
             f"[b]crop={cw}:{ch}:{cx}:{cy},scale={pw}:{og['picture']['height']}:flags={s}[pic];"
             f"[bg][pic]overlay={(w - pw) // 2}:{og['picture']['y']},ass={ass_name}[out]")
    return ["ffmpeg", "-y", "-v", "error", "-i", frame_path, "-filter_complex", graph, "-map", "[out]",
            "-frames:v", "1", "-q:v", str(og["jpeg_qscale"]), out_path]


def crop_cmd(og, crop, src, out_path):
    top, _ = centre_box(og, crop["height"])
    sw = crop["scale_width"]
    sh = round(crop["height"] * sw / og["width"] / 2) * 2
    vf = f"crop={og['width']}:{crop['height']}:0:{top},scale={sw}:{sh}:flags={og['scale']}"
    return ["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf, "-frames:v", "1", "-q:v", str(og["jpeg_qscale"]),
            out_path]


def build(root=ROOT, crops=False, run=subprocess.run):
    site = load(root, "site.json")
    og = site["og_build"]
    text = words(og, load(root, "film.json"), load(root, "captions.en.json"), load(root, "bands.json"),
                 site["domain"])
    problems = check_layout(og, text)
    if problems:
        raise OgError("; ".join(problems))
    out = os.path.join(root, og["out"])
    written = [(out, og["max_bytes"])]
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "og.ass"), "w", encoding="utf-8") as f:
            f.write(og_ass(og, text, load(root, "film.json")["captions"]))
        run(og_cmd(og, os.path.join(root, og["frame"]), "og.ass", out), check=True, cwd=tmp)
    if crops:
        for crop in og["crops"].values():
            dest = os.path.join(root, crop["out"])
            run(crop_cmd(og, crop, out, dest), check=True)
            written.append((dest, og["crop_max_bytes"]))
    for path, limit in written:
        if os.path.getsize(path) > limit:
            raise OgError(f"{os.path.relpath(path, root)} is {os.path.getsize(path)} bytes, over {limit}")
    return [os.path.relpath(p, root) for p, _ in written]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--crops", action="store_true", help="also write the centre 1:1 and 1.91:1 crops")
    args = ap.parse_args(argv)
    try:
        for path in build(crops=args.crops):
            print(path, os.path.getsize(os.path.join(ROOT, path)))
    except OgError as e:
        print(f"og image stopped: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
