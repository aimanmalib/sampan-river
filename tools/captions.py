"""Burned-in captions (ASS) and the SRT, from the single source config/captions.en.json (decision 0001, KM6).

Style values (font, size, colours, outline, bottom margin, line length) come from config/film.json `captions` and the
end card text from `end_card`, per version (`16x9` or `9x16`). The end card text is drawn by this code, never by the
video model; it is rendered into the clean master, the captions only into the final file.
Narrated versions (decision 0012): cue times come from the voice (tools/narrate.py --retime) and the SRT is held to the
limits in config/voice.json `srt` (characters per line, lines, characters per second, minimum length, no overlap).
Usage: python3 tools/captions.py <16x9|9x16> <out_dir> | srt <film|short> <out.srt>
"""
import json
import os
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTIONS = os.path.join(ROOT, "config", "captions.en.json")
FILM = os.path.join(ROOT, "config", "film.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ass_colour(hex_rgb, alpha=0):
    """'#RRGGBB' -> ASS '&HAABBGGRR'."""
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"colour {hex_rgb!r} is not #RRGGBB")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def wrap(text, width):
    """Balanced lines of at most `width` characters (two lines of similar length beat one long and one short)."""
    lines = textwrap.wrap(text, width)
    if len(lines) == 2:
        for w in range(len(text) // 2, width + 1):
            even = textwrap.wrap(text, w)
            if len(even) == 2:
                return even
    return lines


def ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _header(width, height, styles):
    fields = ("Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
              "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
              "MarginL, MarginR, MarginV, Encoding")
    rows = "\n".join("Style: " + ",".join(str(v) for v in s) for s in styles)
    return ("[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
            f"PlayResX: {width}\nPlayResY: {height}\n\n[V4+ Styles]\nFormat: {fields}\n{rows}\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def _style(name, font, size, colour, outline_colour, bold, outline, shadow, align, margin_v, margin_lr):
    return (name, font, size, ass_colour(colour), ass_colour(colour), ass_colour(outline_colour),
            ass_colour(outline_colour, 0x60), -1 if bold else 0, 0, 0, 0, 100, 100, 0, 0, 1, outline, shadow,
            align, margin_lr, margin_lr, margin_v, 1)


def caption_lines(cues, width_chars):
    """[(start, end, [lines])] for every cue, wrapped to the version's line length."""
    out = []
    for c in sorted(cues, key=lambda c: c["start"]):
        lines = wrap(c["text"], width_chars)
        if len(lines) > 2:
            raise ValueError(f"cue at {c['start']} s needs {len(lines)} lines (max 2): {c['text']}")
        out.append((float(c["start"]), float(c["end"]), lines))
    return out


def captions_ass(cues, film, version):
    o, c = film["output"][version], film["captions"]
    style = _style("Caption", c["font"], c["size"][version], c["primary_colour"], c["outline_colour"], c["bold"],
                   c["outline_px"], c["shadow_px"], 2, c["margin_v"][version], int(o["width"] * 0.06))
    events = "".join(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Caption,,0,0,0,," + "\\N".join(lines) + "\n"
                     for a, b, lines in caption_lines(cues, c["max_chars_per_line"][version]))
    return _header(o["width"], o["height"], [style]) + events


def endcard_ass(film, version, film_end_s):
    """End card lines centred: first line large, the rest smaller, fading in at `end_card.start_s`."""
    o, e = film["output"][version], film["end_card"]
    big, small = e["size"][version]
    styles = [_style(n, e["font"], s, e["colour"], e["outline_colour"], True, e["outline_px"], 0, 5, 0, 40)
              for n, s in (("CardTitle", big), ("CardLine", small))]
    fade = int(e["fade_in_s"] * 1000)
    t0, cy = float(e["start_s"]), o["height"] // 2
    events = []
    for i, line in enumerate(e["lines"]):
        y = cy - big // 2 if i == 0 else cy + big // 2 + (i - 1) * int(small * 1.4) + small // 2
        name = "CardTitle" if i == 0 else "CardLine"
        events.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(film_end_s)},{name},,0,0,0,,"
                      f"{{\\fad({fade},0)\\pos({o['width'] // 2},{y})}}{line}\n")
    return _header(o["width"], o["height"], styles) + "".join(events)


def srt(cues, width_chars):
    return "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n" + "\n".join(lines) + "\n\n"
                   for i, (a, b, lines) in enumerate(caption_lines(cues, width_chars), 1))


def srt_problems(cues, lim):
    """Every way the cues break the SRT limits; empty = pass."""
    out, cues = [], sorted(cues, key=lambda c: c["start"])
    for i, (a, b, lines) in enumerate(caption_lines(cues, lim["max_chars_per_line"]), 1):
        if len(lines) > lim["max_lines"] or any(len(x) > lim["max_chars_per_line"] for x in lines):
            out.append(f"cue {i}: {len(lines)} lines, longest {max(len(x) for x in lines)} characters")
        if b - a < lim["min_s"] - 1e-6:
            out.append(f"cue {i}: {b - a:.2f} s < {lim['min_s']} s")
        elif len(" ".join(lines)) / (b - a) > lim["max_cps"]:
            out.append(f"cue {i}: {len(' '.join(lines)) / (b - a):.1f} characters/s > {lim['max_cps']}")
        if i < len(cues) and b > float(cues[i]["start"]) + 1e-6:
            out.append(f"cue {i}: ends at {b} s after cue {i + 1} starts")
    return out


def dump_cues(doc):
    """Caption file text with one cue per line (the layout of config/captions*.json)."""
    rows = ",\n".join("    " + json.dumps(c, ensure_ascii=False) for c in doc["cues"])
    head = "".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},\n" for k, v in doc.items() if k != "cues")
    return "{\n" + head + '  "cues": [\n' + rows + "\n  ]\n}\n"


def write_srt(which, out_path, voice_cfg=None):
    """SRT of the film or the short, refused when it breaks the limits."""
    voice_cfg = voice_cfg or load(os.path.join(ROOT, "config", "voice.json"))
    path = CAPTIONS if which == "film" else os.path.join(ROOT, load(os.path.join(ROOT, "config", "short.json"))["captions"])
    cues, lim = load(path)["cues"], voice_cfg["srt"]
    bad = srt_problems(cues, lim)
    if bad:
        raise ValueError("; ".join(bad))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(srt(cues, lim["max_chars_per_line"]))
    return out_path


def write(out_dir, version, film=None, cues=None):
    """Write the three subtitle files for `version`; returns their paths."""
    film = film or load(FILM)
    cues = cues if cues is not None else load(CAPTIONS)["cues"]
    os.makedirs(out_dir, exist_ok=True)
    end = float(film["duration_s"]["target"])
    paths = {"captions": os.path.join(out_dir, f"captions-{version}.ass"),
             "endcard": os.path.join(out_dir, f"endcard-{version}.ass"),
             "srt": os.path.join(out_dir, "captions.en.srt")}
    texts = {"captions": captions_ass(cues, film, version), "endcard": endcard_ass(film, version, end),
             "srt": srt(cues, film["captions"]["max_chars_per_line"]["16x9"])}
    for k, p in paths.items():
        with open(p, "w", encoding="utf-8") as f:
            f.write(texts[k])
    return paths


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "srt" and sys.argv[2] in ("film", "short"):
        print(write_srt(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) == 3 and sys.argv[1] in ("16x9", "9x16"):
        print(json.dumps(write(sys.argv[2], sys.argv[1])))
    else:
        sys.exit(__doc__.strip().splitlines()[-1])
