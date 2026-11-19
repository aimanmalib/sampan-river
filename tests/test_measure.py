"""Measurement parsing, caption pixel check logic, verdict and MEASURED.md table update (offline)."""
import json
import os
import unittest

import numpy as np

from tools import measure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUES = [{"start": 1.0, "end": 3.0}, {"start": 5.0, "end": 6.0}, {"start": 6.1, "end": 8.0}]


def film():
    with open(os.path.join(ROOT, "config", "film.json"), encoding="utf-8") as f:
        d = json.load(f)
    d["duration_s"]["target"] = 10.0
    return d


def result(**over):
    r = {"version": "16x9", "probe": {"width": 1920, "height": 1080, "fps": 24.0, "duration_s": 60.0, "video_s": 60.0,
                                      "audio": True, "audio_s": 60.0, "video_codec": "h264", "profile": "High",
                                      "pix_fmt": "yuv420p"},
         "lufs_i": -14.0, "true_peak_db": -1.5, "silences": [], "whisper_words": 0,
         "captions": [{"kind": "cue", "index": 0, "t": 2.0, "diff": 9.0, "ok": True},
                      {"kind": "gap", "index": 0, "t": 0.5, "diff": 0.1, "ok": True}], "sha256": "a" * 64}
    r.update(over)
    return r


class MeasureTest(unittest.TestCase):
    def test_ebur128_summary(self):
        err = ("t: 1 M: -20\n[Parsed_ebur128_0 @ 0x1] Summary:\n\n  Integrated loudness:\n    I:         -14.1 LUFS\n"
               "    Threshold: -24.2 LUFS\n\n  True peak:\n    Peak:       -1.6 dBFS\n")
        self.assertEqual(measure.parse_ebur128(err), (-14.1, -1.6))
        with self.assertRaises(ValueError):
            measure.parse_ebur128("nothing")

    def test_silences_open_at_end_runs_to_limit(self):
        err = "silence_start: 0.5\nsilence_end: 3.2 | silence_duration: 2.7\nsilence_start: 13.9\n"
        self.assertEqual(measure.parse_silences(err, 15), [(0.5, 3.2), (13.9, 15)])

    def test_sample_times_cue_middles_and_gaps_over_minimum(self):
        got = measure.sample_times(CUES, 10.0, 0.3)
        self.assertEqual([t for k, _, t in got if k == "cue"], [2.0, 5.5, 7.05])
        self.assertEqual([t for k, _, t in got if k == "gap"], [0.5, 4.0, 9.0])  # 6.0..6.1 is too short

    def test_band_diff_only_counts_the_band(self):
        a = np.zeros((100, 10), dtype=np.int16)
        b = a.copy()
        b[:50] = 200
        self.assertEqual(measure.band_diff(a, b, (0.5, 1.0)), 0.0)
        b[90:] = 100
        self.assertAlmostEqual(measure.band_diff(a, b, (0.5, 1.0)), 20.0)

    def test_caption_check_flags_missing_and_stray_captions(self):
        f = film()
        m = f["measure"]
        ok = measure.caption_check("c", "f", CUES, f, "16x9", diff=lambda t: m["in_cue_min"] + 5 if 1 <= t <= 8 and t != 4.0 else 0)
        self.assertTrue(all(r["ok"] for r in ok))
        missing = measure.caption_check("c", "f", CUES, f, "16x9", diff=lambda t: 0)
        self.assertEqual([r["ok"] for r in missing if r["kind"] == "cue"], [False] * 3)
        stray = measure.caption_check("c", "f", CUES, f, "16x9", diff=lambda t: m["in_cue_min"] + 5)
        self.assertEqual([r["ok"] for r in stray if r["kind"] == "gap"], [False] * 3)

    def test_verdict_names_each_failed_limit(self):
        f = film()
        f["duration_s"].update(min=45, max=75)
        f["audio"]["speech_check"]["expect"] = "none"
        self.assertEqual(measure.verdict(result(), f), [])
        bad = result(lufs_i=-16.0, true_peak_db=-0.5, whisper_words=2, silences=[(1.0, 4.0)])
        bad["probe"] = dict(bad["probe"], audio_s=59.5, fps=25.0)
        bad["captions"][0]["ok"] = False
        self.assertEqual(measure.verdict(bad, f), ["fps", "audio", "lufs", "true_peak", "silence", "speech", "captions"])

    def test_upsert_creates_then_replaces_row_and_detail(self):
        md = "# Measured\n\nIntro.\n"
        r = result(fails=[])
        once = measure.upsert(md, r)
        self.assertIn("| " + " | ".join(measure.COLUMNS) + " |", once)
        self.assertIn("| 16x9 | 1920 | 1080 | 60.0 | yes | -14.0 | -1.5 | 0 | - | 1/1 | " + "a" * 64 + " |", once)
        twice = measure.upsert(once, result(lufs_i=-13.8, fails=[]))
        self.assertEqual(twice.count("| 16x9 |"), 1)
        self.assertEqual(twice.count("<!-- detail:16x9 -->"), 1)
        self.assertIn("| -13.8 |", twice)
        both = measure.upsert(twice, result(version="9x16", fails=[]))
        rows = [ln for ln in both.splitlines() if ln.startswith("| 16x9 |") or ln.startswith("| 9x16 |")]
        self.assertEqual(len(rows), 2)
        self.assertLess(both.index("| 9x16 |"), both.index("<!-- detail:16x9 -->"))

    def test_narrated_version_needs_the_script_and_silent_copy_needs_silence(self):
        f = film()
        f["duration_s"].update(min=45, max=75)
        sc = f["audio"]["speech_check"]
        self.assertEqual(measure.split_version("16x9" + sc["silent_suffix"], f), ("16x9", False))
        self.assertEqual(measure.split_version("16x9", f), ("16x9", sc["expect"] == "script"))
        f["audio"]["speech_check"]["expect"] = "script"
        heard = result(whisper_words=40, speech_match=0.97)
        self.assertEqual(measure.verdict(heard, f), [])
        self.assertEqual(measure.verdict(result(whisper_words=40, speech_match=0.5), f), ["speech_match"])
        self.assertEqual(measure.verdict(result(whisper_words=0), f), ["speech_match"])
        silent = "16x9" + sc["silent_suffix"]
        self.assertEqual(measure.verdict(result(version=silent), f), [])
        self.assertEqual(measure.verdict(result(version=silent, whisper_words=3), f), ["speech"])
        row = measure.table_row(dict(heard, fails=[]))
        self.assertIn("| 40 | 0.97 | 1/1 |", row)

    def test_old_table_gains_the_speech_match_column(self):
        old = ("# M\n\n| version | width | height | duration_s | audio | lufs_i | true_peak_db | whisper_words | "
               "caption_cues | sha256 |\n|---|---|---|---|---|---|---|---|---|---|\n"
               "| 16x9 | 1920 | 1080 | 60.0 | yes | -13.9 | -1.5 | 0 | 10/10 | " + "b" * 64 + " |\n\nafter | x |\n")
        new = measure.migrate(old)
        self.assertIn("| " + " | ".join(measure.COLUMNS) + " |", new)
        self.assertIn("|" + "---|" * len(measure.COLUMNS), new)
        self.assertIn("| 0 | - | 10/10 |", new)
        self.assertIn("after | x |", new)
        self.assertEqual(measure.migrate(new), new)
        merged = measure.upsert(old, result(fails=[], whisper_words=30, speech_match=0.9))
        self.assertEqual(merged.count("| 16x9 |"), 1)
        self.assertIn("| 30 | 0.9 |", merged)


if __name__ == "__main__":
    unittest.main()
