"""How a source clip fills the output frame, per version (config/film.json `edit.layout`).

Modes:
- `cover`: scale the clip to the output size (same aspect).
- `blur_fill` (decision 0006): the landscape clip at full output width over a blurred, dimmed copy of the same frame.
- `crop_fill` (decision 0007): a `crop_aspect` box (for example 1:1) cut from the landscape clip, scaled with the
  output scaler to the full output width, over the same blurred background. The box follows the subject: `centre_x`
  gives, per accepted clip file, keyframes [t, x] (t in seconds from the start of the shot's window, x the box centre in
  source pixels); between keyframes the centre moves linearly, after the last one it holds. A box that would leave the
  source frame is an error, never clamped silently.
"""


class LayoutError(ValueError):
    pass


def _even(v):
    return int(round(v / 2)) * 2


def source_size(film, version):
    src = film["ve"]["resolution"][film["edit"]["orientation"][version]]
    return tuple(int(v) for v in src.split("x"))


def crop_size(film, version, aspect=None):
    """(w, h) of the crop box in source pixels: full source height, width from `crop_aspect` [w, h]."""
    sw, sh = source_size(film, version)
    aw, ah = aspect or film["edit"]["layout"][version]["crop_aspect"]
    cw = _even(sh * aw / ah)
    if not 0 < cw <= sw:
        raise LayoutError(f"{version}: crop aspect {aw}:{ah} does not fit the {sw}x{sh} source")
    return cw, sh


def picture_box(film, version, mode=None, aspect=None):
    """(x, y, w, h) of the source picture inside the output frame."""
    o, lay = film["output"][version], film["edit"]["layout"][version]
    mode = mode or lay["mode"]
    if mode == "cover":
        return 0, 0, o["width"], o["height"]
    if mode == "blur_fill":
        sw, sh = source_size(film, version)
    elif mode == "crop_fill":
        sw, sh = crop_size(film, version, aspect)
    else:
        raise LayoutError(f"{version}: unknown layout {mode}")
    w = o["width"]
    h = _even(w * sh / sw)
    if h > o["height"]:
        raise LayoutError(f"{version}: a {sw}x{sh} picture does not fit the width")
    return 0, _even((o["height"] - h) * lay["picture_y_ratio"]), w, h


def keyframes(film, version, clip, aspect=None):
    """Checked [(t, left_x)] for the clip: times start at 0 and rise, every box stays inside the source frame."""
    lay = film["edit"]["layout"][version]
    keys = lay.get("centre_x", {}).get(clip)
    if not keys:
        raise LayoutError(f"{version}: no centre_x keyframes for {clip}")
    sw, _ = source_size(film, version)
    cw, _ = crop_size(film, version, aspect)
    out, last_t = [], None
    for t, cx in keys:
        if (last_t is None and t != 0) or (last_t is not None and t <= last_t):
            raise LayoutError(f"{clip}: keyframe times must start at 0 and rise ({t})")
        left = cx - cw / 2
        if left < 0 or left + cw > sw:
            raise LayoutError(f"{clip}: a {cw} px box centred at {cx} leaves the {sw} px source frame")
        out.append((float(t), int(round(left))))
        last_t = t
    return out


def left_at(keys, t):
    """Box left edge at time t (linear between keyframes, held after the last one)."""
    for (t0, x0), (t1, x1) in zip(keys, keys[1:]):
        if t < t1:
            return x0 + (x1 - x0) * max(0.0, t - t0) / (t1 - t0)
    return keys[-1][1]


def x_expr(keys):
    """The same function as left_at() as an ffmpeg expression in t (commas escaped for a filter graph)."""
    expr = str(keys[-1][1])
    for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
        expr = f"if(lt(t\\,{t1:g})\\,{x0}+({x1 - x0})*(t-{t0:g})/{t1 - t0:g}\\,{expr})"
    return expr


def segment_graph(film, version, i, clip=None):
    """Filter chain for input i -> [v<i>] at the output size, fps and pixel format."""
    o, fps, lay = film["output"][version], film["edit"]["fps"], film["edit"]["layout"][version]
    if lay["mode"] == "cover":
        return f"[{i}:v]scale={o['width']}:{o['height']}:flags={o['scale']},setsar=1,fps={fps},format=yuv420p[v{i}]"
    x, y, w, h = picture_box(film, version)
    fg = ""
    if lay["mode"] == "crop_fill":
        cw, ch = crop_size(film, version)
        fg = f"crop={cw}:{ch}:'{x_expr(keyframes(film, version, clip))}':0,"
    bw, bh = _even(o["width"] * lay["background_scale"]), _even(o["height"] * lay["background_scale"])
    return (f"[{i}:v]setsar=1,fps={fps},split=2[b{i}][f{i}];"
            f"[b{i}]scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=bicubic,crop={bw}:{bh},"
            f"boxblur={lay['blur_radius']}:2,eq=brightness={lay['background_brightness']},"
            f"scale={o['width']}:{o['height']}:flags=bicubic[bg{i}];"
            f"[f{i}]{fg}scale={w}:{h}:flags={o['scale']}[fg{i}];"
            f"[bg{i}][fg{i}]overlay={x}:{y},format=yuv420p[v{i}]")
