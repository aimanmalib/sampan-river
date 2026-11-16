"""The edit (M4/M5): accepted clips -> clean master -> burned captions + mix -> final file, all with ffmpeg.

1. Clean master: each shot's `window_s` from its accepted clip (config/shots.json), scaled to the output size with the
   scaler named in config/film.json `output` (lanczos), concatenated in `film_s` order; the last frame is held for the
   end card, dimmed, and the end card text (tools/captions.py) is drawn over it. No captions, no audio.
   `edit.layout` per version: `cover` scales the clip to the frame; `blur_fill` (9:16 from landscape clips, decision
   0006) puts the clip at full width over a blurred, dimmed copy of the same frame.
2. Final: the clean master with the captions burned in, the audio mix (`edit.mix`) through two-pass loudnorm to
   `audio.lufs_target` with the true peak `edit.loudnorm.true_peak_margin_db` under `audio.true_peak_max_db`.
   H.264 High yuv420p, AAC 48 kHz stereo, faststart.
Usage: python3 tools/edit.py <16x9|9x16>   (writes clean-<v>.mp4 and sampan-river-<v>.mp4 to `edit.out_dir`)
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import captions, mix  # noqa: E402

SHOTS = os.path.join(ROOT, "config", "shots.json")


class EditError(ValueError):
    pass


def plan(film, shots_cfg, version):
    """Segments [(clip, window_s, film_s)] for the version, checked to tile 0..end_card.start_s with no gap."""
    orientation = film["edit"]["orientation"][version]
    try:
        segs = mix.segments(shots_cfg, orientation)
    except mix.MixError as e:
        raise EditError(str(e)) from e
    t = 0.0
    for clip, _, (f0, f1) in segs:
        if abs(f0 - t) > 1e-6:
            raise EditError(f"{clip}: starts at {f0} s, previous shot ends at {t} s")
        t = f1
    card = float(film["end_card"]["start_s"])
    if abs(t - card) > 1e-6:
        raise EditError(f"shots end at {t} s but the end card starts at {card} s")
    if not card < float(film["duration_s"]["target"]):
        raise EditError("end card starts after the film ends")
    return segs


def picture_box(film, version):
    """(x, y, w, h) of the source picture inside the output frame for the version's layout."""
    o, lay = film["output"][version], film["edit"]["layout"][version]
    if lay["mode"] == "cover":
        return 0, 0, o["width"], o["height"]
    if lay["mode"] != "blur_fill":
        raise EditError(f"{version}: unknown layout {lay['mode']}")
    src = film["ve"]["resolution"][film["edit"]["orientation"][version]]
    sw, sh = (int(v) for v in src.split("x"))
    w = o["width"]
    h = int(round(w * sh / sw / 2)) * 2
    if h > o["height"]:
        raise EditError(f"{version}: source {src} does not fit the width")
    y = int(round((o["height"] - h) * lay["picture_y_ratio"] / 2)) * 2
    return 0, y, w, h


def segment_graph(film, version, i):
    """Filter chain for input i -> [v<i>] at the output size, fps and pixel format."""
    o, fps, lay = film["output"][version], film["edit"]["fps"], film["edit"]["layout"][version]
    if lay["mode"] == "cover":
        return f"[{i}:v]scale={o['width']}:{o['height']}:flags={o['scale']},setsar=1,fps={fps},format=yuv420p[v{i}]"
    head = f"[{i}:v]setsar=1,fps={fps}"
    x, y, w, h = picture_box(film, version)
    bw = int(round(o["width"] * lay["background_scale"] / 2)) * 2
    bh = int(round(o["height"] * lay["background_scale"] / 2)) * 2
    return (f"{head},split=2[b{i}][f{i}];"
            f"[b{i}]scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=bicubic,crop={bw}:{bh},"
            f"boxblur={lay['blur_radius']}:2,eq=brightness={lay['background_brightness']},"
            f"scale={o['width']}:{o['height']}:flags=bicubic[bg{i}];"
            f"[f{i}]scale={w}:{h}:flags={o['scale']}[fg{i}];"
            f"[bg{i}][fg{i}]overlay={x}:{y},format=yuv420p[v{i}]")


def clean_graph(film, segs, version, endcard_name):
    """filter_complex for the clean master; input i = segment i, already cut to its window."""
    o, e, fps = film["output"][version], film["end_card"], film["edit"]["fps"]
    total = float(film["duration_s"]["target"])
    card = float(e["start_s"])
    parts = [segment_graph(film, version, i) for i in range(len(segs))]
    joined = "".join(f"[v{i}]" for i in range(len(segs)))
    dim = (f"eq=eval=frame:brightness='if(gte(t,{card}),{e['dim']}*min(1,(t-{card})/{e['dim_fade_s']}),0)'")
    tail = (f"{joined}concat=n={len(segs)}:v=1:a=0,tpad=stop_mode=clone:stop_duration={total - card},{dim},"
            f"ass={endcard_name},fade=t=out:st={total - e['film_fade_out_s']}:d={e['film_fade_out_s']},"
            f"trim=duration={total}[out]")
    return ";".join(parts + [tail])


def clean_cmd(film, segs, version, clips_dir, out_path, endcard_name):
    c = film["edit"]["clean"]
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for clip, (w0, w1), _ in segs:
        cmd += ["-ss", f"{w0:.3f}", "-t", f"{w1 - w0:.3f}", "-i", os.path.join(clips_dir, clip)]
    return cmd + ["-filter_complex", clean_graph(film, segs, version, endcard_name), "-map", "[out]", "-an",
                  "-c:v", "libx264", "-crf", str(c["crf"]), "-preset", c["preset"], "-pix_fmt", "yuv420p", out_path]


def loudnorm_target(film):
    a, ln = film["audio"], film["edit"]["loudnorm"]
    return f"I={a['lufs_target']}:TP={a['true_peak_max_db'] - ln['true_peak_margin_db']}:LRA={ln['lra']}"


def parse_loudnorm(stderr):
    """The JSON block loudnorm prints at the end of pass 1."""
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr)
    if not m:
        raise EditError("loudnorm pass 1 printed no measurement")
    return json.loads(m[-1])


def second_pass(film, measured):
    return (f"loudnorm={loudnorm_target(film)}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true")


def final_cmd(film, clean_path, mix_path, captions_name, audio_filter, out_path):
    f, a = film["edit"]["final"], film["audio"]
    total = float(film["duration_s"]["target"])
    return ["ffmpeg", "-y", "-v", "error", "-i", clean_path, "-i", mix_path, "-filter_complex",
            f"[0:v]ass={captions_name}[v];[1:a]{audio_filter},aresample={a['sample_rate']}[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-profile:v", f["profile"], "-crf", str(f["crf"]),
            "-preset", f["preset"], "-pix_fmt", f["pix_fmt"], "-c:a", f["audio_codec"], "-b:a", f["audio_bitrate"],
            "-ar", str(a["sample_rate"]), "-ac", "2", "-t", f"{total:.3f}", "-movflags", "+faststart",
            "-metadata", f"title={film['title']}", out_path]


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise EditError(f"{cmd[0]} exit {r.returncode}: {r.stderr.strip()[-600:]}")
    return r


def main(argv):
    if len(argv) != 1 or argv[0] not in ("16x9", "9x16"):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    version = argv[0]
    film = captions.load(captions.FILM)
    segs = plan(film, captions.load(SHOTS), version)
    out_dir = os.path.join(ROOT, film["edit"]["out_dir"])
    subs = captions.write(out_dir, version, film)
    clips_dir = os.path.join(ROOT, captions.load(mix.music.CONFIG)["mix"]["clips_dir"])
    clean = os.path.join(out_dir, f"clean-{version}.mp4")
    run(clean_cmd(film, segs, version, clips_dir, clean, os.path.basename(subs["endcard"])), out_dir)
    mix_path = os.path.join(ROOT, film["edit"]["mix"].format(orientation=film["edit"]["orientation"][version]))
    if not os.path.exists(mix_path):
        raise EditError(f"{mix_path} missing: run tools/mix.py first")
    probe = run(["ffmpeg", "-hide_banner", "-i", mix_path, "-af", f"loudnorm={loudnorm_target(film)}:print_format=json",
                 "-f", "null", "-"], out_dir)
    measured = parse_loudnorm(probe.stderr)
    final = os.path.join(out_dir, f"sampan-river-{version}.mp4")
    run(final_cmd(film, clean, mix_path, os.path.basename(subs["captions"]), second_pass(film, measured), final),
        out_dir)
    print(json.dumps({"clean": os.path.relpath(clean, ROOT), "final": os.path.relpath(final, ROOT),
                      "srt": os.path.relpath(subs["srt"], ROOT), "loudnorm_pass1": measured}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
