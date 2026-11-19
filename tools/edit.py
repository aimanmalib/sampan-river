"""The edit (M4/M5): accepted clips -> clean master -> burned captions + mix -> final file, all with ffmpeg.

1. Clean master: each shot's `window_s` from its accepted clip (config/shots.json), scaled to the output size with the
   scaler named in config/film.json `output` (lanczos), concatenated in `film_s` order; the last frame is held for the
   end card, dimmed, and the end card text (tools/captions.py) is drawn over it. No captions, no audio.
   `edit.layout` per version (tools/layout.py): `cover`, `blur_fill` (decision 0006) or `crop_fill` (decision 0007).
2. Final: the clean master with the captions burned in, the audio mix (`edit.mix`) through two-pass loudnorm to
   `audio.lufs_target` with the true peak `edit.loudnorm.true_peak_margin_db` under `audio.true_peak_max_db`.
   H.264 High yuv420p, AAC 48 kHz stereo, faststart.
3. Narrated (decision 0012, `audio.speech_check.expect` = script and config/voice.json `enabled`): the mix is the bed with
   the cached voice takes placed and ducked (tools/narrate.py), before the same loudnorm. In the same pass the silent
   copy `sampan-river-<v><silent_suffix>.mp4` is written: the narrated file's video stream copied unchanged, the bed
   without duck through its own two-pass loudnorm to the same target. The mix stats go to narration-<v>.json for
   tools/measure.py. The voice id (environment variable named in config/voice.json) names the cached takes.
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
from tools import captions, layout, mix  # noqa: E402

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


def clean_graph(film, segs, version, endcard_name):
    """filter_complex for the clean master; input i = segment i, already cut to its window."""
    o, e, fps = film["output"][version], film["end_card"], film["edit"]["fps"]
    total = float(film["duration_s"]["target"])
    card = float(e["start_s"])
    parts = [layout.segment_graph(film, version, i, clip) for i, (clip, _, _) in enumerate(segs)]
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


def _audio_out(film, out_path):
    f, a = film["edit"]["final"], film["audio"]
    total = float(film["duration_s"]["target"])
    return ["-c:a", f["audio_codec"], "-b:a", f["audio_bitrate"], "-ar", str(a["sample_rate"]), "-ac", "2",
            "-t", f"{total:.3f}", "-movflags", "+faststart", "-metadata", f"title={film['title']}", out_path]


def final_cmd(film, clean_path, mix_path, captions_name, audio_filter, out_path):
    f, a = film["edit"]["final"], film["audio"]
    return ["ffmpeg", "-y", "-v", "error", "-i", clean_path, "-i", mix_path, "-filter_complex",
            f"[0:v]ass={captions_name}[v];[1:a]{audio_filter},aresample={a['sample_rate']}[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-profile:v", f["profile"], "-crf", str(f["crf"]),
            "-preset", f["preset"], "-pix_fmt", f["pix_fmt"]] + _audio_out(film, out_path)


def silent_cmd(film, narrated_path, bed_path, audio_filter, out_path):
    """Same picture as the narrated file (video stream copied, not encoded again), the bed without the voice."""
    return ["ffmpeg", "-y", "-v", "error", "-i", narrated_path, "-i", bed_path, "-filter_complex",
            f"[1:a]{audio_filter},aresample={film['audio']['sample_rate']}[a]", "-map", "0:v", "-map", "[a]",
            "-c:v", "copy"] + _audio_out(film, out_path)


def narrated(film, voice_cfg):
    return bool(voice_cfg.get("enabled")) and film["audio"]["speech_check"].get("expect") == "script"


def loudnorm_pass2(film, wav, cwd):
    """Pass 1 of loudnorm on `wav`; returns (measurement, pass-2 filter)."""
    probe = run(["ffmpeg", "-hide_banner", "-i", wav, "-af", f"loudnorm={loudnorm_target(film)}:print_format=json",
                 "-f", "null", "-"], cwd)
    measured = parse_loudnorm(probe.stderr)
    return measured, second_pass(film, measured)


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise EditError(f"{cmd[0]} exit {r.returncode}: {r.stderr.strip()[-600:]}")
    return r


def narration(film, version):
    """(narrated wav, mix stats) for a narrated film, or None when the film is silent."""
    from tools import narrate, voice  # narrate -> short -> edit: imported here to keep the import order simple
    cfg = captions.load(voice.CONFIG)
    if not narrated(film, cfg):
        return None
    voice_id = os.environ.get(cfg["voice_env"])
    if not voice_id:
        raise EditError(f"set {cfg['voice_env']} in the environment (it names the cached takes)")
    res = narrate.build(version, voice_id, film)
    held = [p["id"] for p in res["placed"] if not p["ok"]]
    if held:
        raise EditError(f"lines without a placed take: {', '.join(held)}")
    return res["wav"], res["mix"]


def main(argv):
    if len(argv) != 1 or argv[0] not in ("16x9", "9x16"):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    version = argv[0]
    film = captions.load(captions.FILM)
    segs = plan(film, captions.load(SHOTS), version)
    out_dir = os.path.join(ROOT, film["edit"]["out_dir"])
    bed = os.path.join(ROOT, film["edit"]["mix"].format(orientation=film["edit"]["orientation"][version]))
    if not os.path.exists(bed):
        raise EditError(f"{bed} missing: run tools/mix.py first")
    voiced = narration(film, version)
    subs = captions.write(out_dir, version, film)
    clips_dir = os.path.join(ROOT, captions.load(mix.music.CONFIG)["mix"]["clips_dir"])
    clean = os.path.join(out_dir, f"clean-{version}.mp4")
    run(clean_cmd(film, segs, version, clips_dir, clean, os.path.basename(subs["endcard"])), out_dir)
    measured, ln = loudnorm_pass2(film, voiced[0] if voiced else bed, out_dir)
    final = os.path.join(out_dir, f"sampan-river-{version}.mp4")
    run(final_cmd(film, clean, voiced[0] if voiced else bed, os.path.basename(subs["captions"]), ln, final), out_dir)
    report = {"clean": os.path.relpath(clean, ROOT), "final": os.path.relpath(final, ROOT),
              "srt": os.path.relpath(subs["srt"], ROOT), "loudnorm_pass1": measured}
    if voiced:
        silent = os.path.join(out_dir, f"sampan-river-{version}{film['audio']['speech_check']['silent_suffix']}.mp4")
        bed_measured, bed_ln = loudnorm_pass2(film, bed, out_dir)
        run(silent_cmd(film, final, bed, bed_ln, silent), out_dir)
        with open(os.path.join(out_dir, f"narration-{version}.json"), "w", encoding="utf-8") as f:
            json.dump(voiced[1], f)
        report.update(silent=os.path.relpath(silent, ROOT), mix=voiced[1], loudnorm_pass1_silent=bed_measured)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
