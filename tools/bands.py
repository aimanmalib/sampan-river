"""Native vertical bands (decision 0010): the 9:16 frame works above and below the picture.

The picture box (tools/layout.py `picture_box`) leaves a band above and a band below the 16:9 picture.
- Top band: the caption cues (config/captions*.json, the same source as the SRT) drawn large in the middle of the band.
  On screen each cue is held until the next cue starts (less `hold_gap_s`, at most `hold_max_s` long), so the band is
  not empty while the voice pauses. The SRT keeps the spoken times.
- Bottom band: one large sourced figure with a small label (config/bands.json, per version), for example "$1" /
  "one digital dollar". Every figure with a digit or currency sign names a fact in docs/FACTS.md, except a figure that
  appears in the unsourced hook cue (starts before `duration_s.hook_max_s`).
Style (sizes, positions, line length, colours) = config/film.json `captions.bands.<version>`. Nothing is drawn after the
end card starts except caption cues.
Measured (tools/measure.py): the pixel check per band (inside every interval the final differs from the clean master,
between intervals it does not), `band_cover` = share of 0..end_card.start_s with text in the band, and the WCAG contrast
of the text colour over the clean master background inside each text box.
"""
import os
import re
import textwrap

import numpy as np

from tools import captions, layout

BANDS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "bands.json")
CLAIM = re.compile(r"[0-9$¢]")


class BandError(ValueError):
    pass


def style(film, version):
    """The version's band style, or None when the version has no bands."""
    return film["captions"].get("bands", {}).get(version)


def boxes(film, version):
    """{'top': (y0, y1), 'bottom': (y0, y1)} in output pixels around the picture box."""
    o = film["output"][version]
    _, y, _, h = layout.picture_box(film, version)
    if y <= 0 or y + h >= o["height"]:
        raise BandError(f"{version}: the picture leaves no band above and below")
    return {"top": (0, y), "bottom": (y + h, o["height"])}


def held(cues, st, end_s):
    """[(start, end, text)] the top band shows: each cue held until the next starts (gap), at most hold_max_s."""
    cues = sorted(cues, key=lambda c: c["start"])
    out = []
    for i, c in enumerate(cues):
        a, b = float(c["start"]), float(c["end"])
        nxt = float(cues[i + 1]["start"]) - st["hold_gap_s"] if i + 1 < len(cues) else end_s
        out.append((a, max(b, min(nxt, a + st["hold_max_s"], end_s)), c["text"]))
    return out


def top_lines(text, st):
    lines = textwrap.wrap(text, st["max_chars_per_line"])
    if len(lines) > st["max_lines"]:
        raise BandError(f"top band: {text!r} needs {len(lines)} lines (max {st['max_lines']})")
    return lines


def fits(chars, size, width, film):
    """Text of `chars` characters at `size` px fits the width less the side margins (advance factor from config)."""
    b = film["captions"]["bands"]
    return chars * size * b["advance_em"] <= width * (1 - 2 * b["side_margin"])


def check_figures(rows, cues, facts_text, film):
    """Errors in the bottom band rows; empty = pass (rule above, plus times and width)."""
    hook = " ".join(c["text"] for c in cues if not c.get("fact") and float(c["start"]) < film["duration_s"]["hook_max_s"])
    card, errs = float(film["end_card"]["start_s"]), []
    for i, r in enumerate(rows):
        fig = str(r["figure"])
        if CLAIM.search(fig):
            if r.get("fact"):
                if not re.search(r"`" + re.escape(r["fact"]) + r"`", facts_text):
                    errs.append(f"figure {i + 1} ({fig}): fact {r['fact']} is not in docs/FACTS.md")
            elif fig.strip() not in hook:
                errs.append(f"figure {i + 1} ({fig}): no fact and not in the hook cue")
        if not 0 <= float(r["start"]) < float(r["end"]) <= card:
            errs.append(f"figure {i + 1} ({fig}): times {r['start']}..{r['end']} outside 0..{card}")
        if i and float(r["start"]) < float(rows[i - 1]["end"]):
            errs.append(f"figure {i + 1} ({fig}): overlaps figure {i}")
    return errs


def intervals(film, version, cues, rows):
    """{'top': [(a, b)], 'bottom': [(a, b)]} when each band shows text."""
    st = style(film, version)
    end = float(film["duration_s"]["target"])
    return {"top": [(a, b) for a, b, _ in held(cues, st["top"], end)],
            "bottom": [(float(r["start"]), float(r["end"])) for r in rows]}


def cover(spans, upto):
    """Share of 0..upto covered by the spans (overlaps counted once)."""
    t, total = 0.0, 0.0
    for a, b in sorted((max(0.0, a), min(upto, b)) for a, b in spans):
        if b > max(a, t):
            total += b - max(a, t)
            t = b
    return round(total / upto, 3)


def text_boxes(film, version, cues, rows):
    """[(band, t_mid, (x0, y0, x1, y1))] the box each piece of text occupies, for the contrast check."""
    st, o = style(film, version), film["output"][version]
    bx, adv, out = boxes(film, version), film["captions"]["bands"]["advance_em"], []
    end = float(film["duration_s"]["target"])
    for a, b, text in held(cues, st["top"], end):
        lines, size = top_lines(text, st["top"]), st["top"]["size"]
        cy, h = _y(bx["top"], st["top"]["y_ratio"]), int(len(lines) * size * st["top"]["line_height"])
        w = int(max(map(len, lines)) * size * adv)
        out.append(("top", round((a + b) / 2, 3), _box(o["width"], cy, w, h)))
    for r in rows:
        bo = st["bottom"]
        t = round((float(r["start"]) + float(r["end"])) / 2, 3)
        cy, w = _y(bx["bottom"], bo["figure_y_ratio"]), int(len(str(r["figure"])) * bo["figure_size"] * adv)
        out.append(("bottom", t, _box(o["width"], cy, w, bo["figure_size"])))
        cy, w = _y(bx["bottom"], bo["label_y_ratio"]), int(len(r["label"]) * bo["label_size"] * adv)
        out.append(("bottom", t, _box(o["width"], cy, w, bo["label_size"])))
    return out


def _y(band, ratio):
    return int(band[0] + (band[1] - band[0]) * ratio)


def _box(width, cy, w, h):
    return (max(0, (width - w) // 2), max(0, cy - h // 2), min(width, (width + w) // 2), cy + h // 2)


def ass(film, version, cues, rows):
    """ASS for the final file: top band captions + bottom band figures and labels."""
    st, o, c = style(film, version), film["output"][version], film["captions"]
    bx, fade, end = boxes(film, version), int(st["fade_s"] * 1000), float(film["duration_s"]["target"])
    names = (("BandTop", st["top"]["size"]), ("BandFigure", st["bottom"]["figure_size"]),
             ("BandLabel", st["bottom"]["label_size"]))
    styles = [captions._style(n, c["font"], s, c["primary_colour"], c["outline_colour"], True, st["outline_px"],
                              c["shadow_px"], 5, 0, 0) for n, s in names]
    x, ev = o["width"] // 2, []

    def line(a, b, name, y, text):
        ev.append(f"Dialogue: 0,{captions.ass_time(a)},{captions.ass_time(b)},{name},,0,0,0,,"
                  f"{{\\fad({fade},{fade})\\pos({x},{y})}}{text}\n")
    for a, b, text in held(cues, st["top"], end):
        line(a, b, "BandTop", _y(bx["top"], st["top"]["y_ratio"]), "\\N".join(top_lines(text, st["top"])))
    for r in rows:
        line(float(r["start"]), float(r["end"]), "BandFigure", _y(bx["bottom"], st["bottom"]["figure_y_ratio"]),
             str(r["figure"]))
        line(float(r["start"]), float(r["end"]), "BandLabel", _y(bx["bottom"], st["bottom"]["label_y_ratio"]), r["label"])
    return captions._header(o["width"], o["height"], styles) + "".join(ev)


def check_layout(film, version, cues, rows):
    """Errors in the drawn layout: lines and figures fit the width, text boxes stay inside their band."""
    st, o, errs = style(film, version), film["output"][version], []
    bx = boxes(film, version)
    for c in cues:
        try:
            lines = top_lines(c["text"], st["top"])
        except BandError as e:
            return errs + [str(e)]
        if not fits(max(map(len, lines)), st["top"]["size"], o["width"], film):
            errs.append(f"top band: {c['text']!r} is wider than the frame")
    for r in rows:
        for txt, size in ((str(r["figure"]), st["bottom"]["figure_size"]), (r["label"], st["bottom"]["label_size"])):
            if not fits(len(txt), size, o["width"], film):
                errs.append(f"bottom band: {txt!r} at {size} px is wider than the frame")
    for band, _, (_, y0, _, y1) in text_boxes(film, version, cues, rows):
        if y0 < bx[band][0] or y1 > bx[band][1]:
            errs.append(f"{band} band: a text box {y0}..{y1} leaves the band {bx[band]}")
    return errs


def luminance(rgb):
    """WCAG 2.x relative luminance of sRGB values in 0..255 (array, last axis = R, G, B)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def contrast(text_hex, background_rgb):
    """WCAG contrast ratio of the text colour over the mean luminance of a background region."""
    h = text_hex.lstrip("#")
    lt = float(luminance([int(h[i:i + 2], 16) for i in (0, 2, 4)]))
    lb = float(np.mean(luminance(background_rgb)))
    hi, lo = max(lt, lb), min(lt, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def frame(path, t, width, height, pix_fmt="gray"):
    """One decoded frame at t seconds: gray -> (h, w) int16, rgb24 -> (h, w, 3) uint8."""
    import subprocess
    ch = 3 if pix_fmt == "rgb24" else 1
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", pix_fmt, "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.uint8)[:width * height * ch]
    return a.reshape(height, width, 3) if ch == 3 else a.reshape(height, width).astype(np.int16)


def rows_for(version, doc=None):
    if doc is None:
        doc = captions.load(BANDS)
    if version not in doc:
        raise BandError(f"config/bands.json has no rows for {version}")
    return doc[version]


def measure(clean, final, film, version, cues, rows, sample_times, diff=None, rgb=None):
    """Pixel check per band, band_cover and contrast; diff(t, band) and rgb(t) are injectable for tests.

    Returns {'captions': [{kind, index, t, diff, ok}], 'cover': {band: share}, 'contrast': [(band, t, ratio)],
    'fails': [...], 'md': [markdown lines]}."""
    m, o = film["measure"], film["output"][version]
    bx, card = boxes(film, version), float(film["end_card"]["start_s"])
    if diff is None:
        def diff(t, band):
            a, b = frame(clean, t, o["width"], o["height"]), frame(final, t, o["width"], o["height"])
            return float(np.mean(np.abs(a[band[0]:band[1]] - b[band[0]:band[1]])))
    if rgb is None:
        def rgb(t):
            return frame(clean, t, o["width"], o["height"], "rgb24")
    spans, checks = intervals(film, version, cues, rows), []
    for band in ("top", "bottom"):
        fake = [{"start": a, "end": b} for a, b in spans[band]]
        for kind, i, t in sample_times(fake, float(film["duration_s"]["target"]), m["min_gap_s"]):
            d = round(diff(t, bx[band]), 2)
            ok = d > m["in_cue_min"] if kind == "cue" else d < m["out_cue_max"]
            checks.append({"kind": f"{band} {kind}", "index": i, "t": t, "diff": d, "ok": ok})
    cov = {band: cover(spans[band], card) for band in ("top", "bottom")}
    colour = film["captions"]["primary_colour"]
    con = [(band, t, contrast(colour, rgb(t)[y0:y1, x0:x1].reshape(-1, 3)))
           for band, t, (x0, y0, x1, y1) in text_boxes(film, version, cues, rows)]
    fails = (["band_cover"] if min(cov.values()) < m["band_cover_min"] else []) + \
            (["contrast"] if min(c for *_, c in con) < m["contrast_min"] else [])
    md = ["", f"Bands (decision 0010): share of 0..{card:g} s with text, minimum {m['band_cover_min']}.", "",
          "| version | band | cover | min |", "|---|---|---|---|"]
    md += [f"| {{version}} | {b} | {v} | {m['band_cover_min']} |" for b, v in cov.items()]
    md += ["", f"Text contrast (WCAG, text {colour} over the clean master inside each text box), minimum "
           f"{m['contrast_min']}.", "", "| band | t (s) | contrast |", "|---|---|---|"]
    md += [f"| {b} | {t} | {c} |" for b, t, c in con]
    return {"captions": checks, "cover": cov, "contrast": con, "fails": fails, "md": md}
