"""Placement, retiming, duck envelope and mix stats (decision 0012), on synthetic signals: a sine stands for the voice."""
import json
import os
import unittest

import numpy as np

from tools import captions, narrate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 8000


def cfg():
    with open(os.path.join(ROOT, "config", "voice.json"), encoding="utf-8") as f:
        return json.load(f)


CUES = [{"id": "a", "start": 0.2, "end": 3.0, "text": "One rower takes the river instead."},
        {"id": "b", "start": 4.0, "end": 6.0, "text": "She carries one dollar across."},
        {"id": "c", "start": 6.5, "end": 9.0, "text": "Less than a tenth of a cent."}]


def sine(seconds, f=220.0):
    t = np.arange(int(seconds * SR)) / SR
    return 0.3 * np.sin(2 * np.pi * f * t)


def bed(seconds):
    rng = np.random.default_rng(7)
    y = rng.normal(0, 0.1, (int(seconds * SR), 2))
    return y


class NarrateTest(unittest.TestCase):
    def test_lines_fit_their_windows_or_are_held_back(self):
        c = cfg()
        placed = narrate.place(CUES, {"a": (0.1, 2.0), "b": (0.0, 2.45), "c": (0.2, 9.0)}, c, 10.0)
        a, b, cc = placed
        self.assertEqual((a["at"], a["tempo"], a["ok"]), (0.3, 1.0, True))
        self.assertTrue(b["ok"])
        self.assertGreater(b["tempo"], 1.0)
        self.assertLessEqual(b["tempo"], c["max_tempo"])
        self.assertLessEqual(b["at"] + b["voice_s"], CUES[2]["start"] - c["min_gap_s"] + 1e-3)
        self.assertFalse(cc["ok"])
        for p in placed:
            if p["ok"]:
                self.assertLessEqual(p["voice_s"], p["window_s"] + 1e-3)
        missing = narrate.place(CUES, {"a": (0.1, 2.0)}, c, 10.0)
        self.assertEqual([p["ok"] for p in missing], [True, False, False])

    def test_retimed_cues_follow_the_voice_and_never_overlap(self):
        c = cfg()
        placed = narrate.place(CUES, {"a": (0.1, 0.5), "b": (0.0, 2.45), "c": (0.0, 1.0)}, c, 10.0)
        cues = narrate.retime(CUES, placed, c)
        self.assertEqual(cues[0]["start"], round(placed[0]["at"] - c["lead_s"], 2))
        self.assertGreaterEqual(cues[0]["end"] - cues[0]["start"], c["min_cue_s"] - 1e-6)
        self.assertEqual(cues[1]["end"], cues[2]["start"])
        for x, y in zip(cues, cues[1:]):
            self.assertLessEqual(x["end"], y["start"])
        self.assertEqual(CUES[0]["end"], 3.0)
        self.assertEqual(captions.srt_problems(cues, c["srt"]), [])

    def test_envelope_ducks_inside_and_leaves_the_rest(self):
        c = cfg()
        g = narrate.envelope(10 * SR, SR, [(2.0, 4.0)], c["duck_db"], c["ramp_s"])
        low = 10 ** (-c["duck_db"] / 20)
        self.assertAlmostEqual(g[int(3.0 * SR)], low)
        self.assertEqual(g[int(1.0 * SR)], 1.0)
        self.assertEqual(g[int(6.0 * SR)], 1.0)
        mid = g[int((2.0 - c["ramp_s"] / 2) * SR)]
        self.assertTrue(low < mid < 1.0)
        self.assertTrue(np.all(np.diff(g[int(1.5 * SR):int(2.0 * SR)]) <= 1e-12))

    def test_mix_puts_the_voice_well_over_the_bed(self):
        c = cfg()
        b = bed(10)
        sp = [(2.0, 4.0), (6.0, 8.0)]
        v = narrate.voice_track(len(b), SR, [(2.0, sine(2.0)), (6.0, sine(2.0, 330.0))], c["voice_rms_dbfs"])
        g = narrate.envelope(len(b), SR, sp, c["duck_db"], c["ramp_s"])
        s = narrate.mix_stats(b, v, g, sp, SR, c["ramp_s"])
        self.assertAlmostEqual(s["voice_rms_db"], c["voice_rms_dbfs"], delta=0.3)
        self.assertGreaterEqual(s["gap_db"], 10)
        self.assertLessEqual(abs(s["bed_outside_change_db"]), 0.5)
        flat = narrate.mix_stats(b, v, np.ones(len(b)), sp, SR, c["ramp_s"])
        self.assertLess(flat["gap_db"], 10)
        y = narrate.narrate(b, v, g, -1.0, SR, 0.01)
        self.assertEqual(y.shape, b.shape)
        self.assertLessEqual(np.max(np.abs(y)), 10 ** (-1 / 20) + 1e-9)
        outside = slice(0, int(1.5 * SR))
        self.assertTrue(np.allclose(y[outside], b[outside]))

    def test_mix_table_row_is_added_then_replaced(self):
        s = {"voice_rms_db": -16.0, "bed_under_voice_db": -30.1, "gap_db": 14.1, "bed_outside_change_db": 0.0}
        md = narrate.upsert_mix("# M\n\ntext\n", "preview-16x9", s)
        self.assertIn("| " + " | ".join(narrate.MIX_COLUMNS) + " |", md)
        md = narrate.upsert_mix(md, "preview-16x9", dict(s, gap_db=13.0))
        md = narrate.upsert_mix(md, "16x9", s)
        self.assertEqual(md.count("| preview-16x9 |"), 1)
        self.assertIn("| 13.0 |", md)
        self.assertIn("| 16x9 | -16.0 |", md)

    def test_atempo_only_when_needed(self):
        self.assertEqual(narrate.atempo_filter(1.0), "anull")
        self.assertEqual(narrate.atempo_filter(1.05), "atempo=1.05")


if __name__ == "__main__":
    unittest.main()
