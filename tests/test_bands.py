"""Native vertical bands (decision 0010): layout, figure facts, held captions, cover, contrast, per-band pixel check."""
import copy
import json
import os
import unittest

import numpy as np

from tools import bands, captions, measure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = "| `fact-a` | A sourced claim | source | 2026-11-19 |\n"
CUES = [{"start": 0.2, "end": 3.0, "text": "Sending $5 should not cost $5.", "fact": None},
        {"start": 4.0, "end": 6.0, "text": "A second line that is a little longer.", "fact": None},
        {"start": 20.0, "end": 22.0, "text": "A third line.", "fact": "fact-a"}]
ROWS = [{"start": 0.2, "end": 10.0, "figure": "$5", "label": "to send $5", "fact": None},
        {"start": 12.0, "end": 30.0, "figure": "$1", "label": "one dollar", "fact": "fact-a"}]


def film():
    with open(os.path.join(ROOT, "config", "film.json"), encoding="utf-8") as f:
        return json.load(f)


class BandsTest(unittest.TestCase):
    def setUp(self):
        self.film = film()

    def test_bands_sit_above_and_below_the_picture(self):
        b = bands.boxes(self.film, "9x16")
        self.assertEqual(b["top"][0], 0)
        self.assertEqual(b["bottom"][1], self.film["output"]["9x16"]["height"])
        self.assertGreater(b["bottom"][0], b["top"][1])

    def test_landscape_has_no_bands(self):
        self.assertIsNone(bands.style(self.film, "16x9"))

    def test_sourced_and_hook_figures_pass(self):
        self.assertEqual(bands.check_figures(ROWS, CUES, FACTS, self.film), [])

    def test_figure_without_fact_outside_the_hook_fails(self):
        rows = copy.deepcopy(ROWS)
        rows[1]["fact"] = None
        self.assertEqual(len(bands.check_figures(rows, CUES, FACTS, self.film)), 1)

    def test_figure_with_unknown_fact_fails(self):
        rows = copy.deepcopy(ROWS)
        rows[1]["fact"] = "fact-missing"
        self.assertIn("not in docs/FACTS.md", bands.check_figures(rows, CUES, FACTS, self.film)[0])

    def test_figure_after_the_end_card_or_overlapping_fails(self):
        rows = copy.deepcopy(ROWS) + [{"start": 29.0, "end": 58.0, "figure": "big", "label": "x", "fact": None}]
        errs = bands.check_figures(rows, CUES, FACTS, self.film)
        self.assertTrue(any("outside" in e for e in errs) and any("overlaps" in e for e in errs))

    def test_captions_are_held_until_the_next_cue(self):
        st = self.film["captions"]["bands"]["9x16"]["top"]
        h = bands.held(CUES, st, 60.0)
        self.assertAlmostEqual(h[0][1], 4.0 - st["hold_gap_s"])
        self.assertAlmostEqual(h[1][1], 4.0 + st["hold_max_s"])
        self.assertAlmostEqual(h[2][1], 20.0 + st["hold_max_s"])

    def test_cover_counts_overlaps_once_and_clips_to_the_window(self):
        self.assertEqual(bands.cover([(0, 10), (5, 15), (40, 70)], 50.0), round(25 / 50, 3))

    def test_layout_of_the_real_config_fits(self):
        cues = captions.load(captions.CAPTIONS)["cues"]
        self.assertEqual(bands.check_layout(self.film, "9x16", cues, bands.rows_for("9x16")), [])

    def test_too_wide_figure_and_text_outside_the_band_fail(self):
        rows = copy.deepcopy(ROWS)
        rows[0]["figure"] = "$123456789"
        f = copy.deepcopy(self.film)
        f["captions"]["bands"]["9x16"]["bottom"]["label_y_ratio"] = 0.99
        errs = bands.check_layout(f, "9x16", CUES, rows)
        self.assertTrue(any("wider" in e for e in errs) and any("leaves the band" in e for e in errs))

    def test_four_line_caption_fails(self):
        cues = [{"start": 0, "end": 2, "text": "word " * 20, "fact": None}]
        self.assertTrue(bands.check_layout(self.film, "9x16", cues, ROWS))

    def test_wcag_contrast(self):
        self.assertEqual(bands.contrast("#FFFFFF", np.zeros((4, 3))), 21.0)
        self.assertEqual(bands.contrast("#FFFFFF", np.full((4, 3), 255)), 1.0)
        self.assertAlmostEqual(bands.contrast("#FFFFFF", np.full((1, 3), 118)), 4.54, places=1)

    def test_ass_draws_captions_top_and_figures_bottom(self):
        text = bands.ass(self.film, "9x16", CUES, ROWS)
        b = bands.boxes(self.film, "9x16")
        ys = {ln.split(",,")[-1].split("}")[1]: int(ln.split("\\pos(")[1].split(",")[1].split(")")[0])
              for ln in text.splitlines() if ln.startswith("Dialogue")}
        self.assertLess(ys["A third line."], b["top"][1])
        self.assertGreater(ys["$1"], b["bottom"][0])
        self.assertGreater(ys["one dollar"], ys["$1"])

    def test_measure_passes_and_fails_per_band(self):
        f, bx = self.film, bands.boxes(self.film, "9x16")
        spans = bands.intervals(f, "9x16", CUES, ROWS)

        def diff(t, band):
            key = "top" if band == bx["top"] else "bottom"
            return 30.0 if any(a <= t <= b for a, b in spans[key]) else 0.5

        dark = np.zeros((f["output"]["9x16"]["height"], f["output"]["9x16"]["width"], 3), dtype=np.uint8)
        r = bands.measure("c", "f", f, "9x16", CUES, ROWS, measure.sample_times, diff, lambda t: dark)
        self.assertTrue(all(x["ok"] for x in r["captions"]))
        self.assertNotIn("contrast", r["fails"])
        self.assertTrue(any(x["kind"] == "bottom gap" for x in r["captions"]))
        self.assertIn("| {version} | top |", "\n".join(r["md"]))
        light = dark + 200
        r = bands.measure("c", "f", f, "9x16", CUES, ROWS, measure.sample_times, lambda t, b: 0.0, lambda t: light)
        self.assertIn("contrast", r["fails"])
        self.assertFalse(any(x["ok"] for x in r["captions"] if x["kind"].endswith("cue")))

    def test_low_cover_fails(self):
        rows = [dict(ROWS[0], end=2.0)]
        r = bands.measure("c", "f", self.film, "9x16", CUES, rows, measure.sample_times, lambda t, b: 30.0,
                          lambda t: np.zeros((1920, 1080, 3), dtype=np.uint8))
        self.assertIn("band_cover", r["fails"])

    def test_verdict_and_detail_carry_band_results(self):
        result = {"version": "9x16", "band_fails": ["contrast"], "band_md": ["| {version} | top | 0.9 | 0.7 |"],
                  "captions": [{"kind": "top cue", "index": 0, "t": 1.0, "diff": 9.0, "ok": True}]}
        self.assertIn("| 9x16 | top | 0.9 | 0.7 |", measure.detail(dict(result, probe=PROBE, silences=[], fails=[])))
        fails = measure.verdict(dict(result, probe=PROBE, lufs_i=-14.0, true_peak_db=-2.0, silences=[],
                                     whisper_words=0, speech_match=0.95), self.film)
        self.assertEqual(fails, ["contrast"])


PROBE = {"width": 1080, "height": 1920, "fps": 24, "duration_s": 60.0, "audio": True, "audio_s": 60.0, "video_s": 60.0,
         "video_codec": "h264", "profile": "High", "pix_fmt": "yuv420p", "audio_codec": "aac", "sample_rate": 48000,
         "channels": 2}


class BurnedCaptionsTest(unittest.TestCase):
    def test_vertical_burns_bands_landscape_keeps_the_line(self):
        f = film()
        cues = captions.load(captions.CAPTIONS)["cues"]
        self.assertIn("BandFigure", captions._burned(cues, f, "9x16"))
        self.assertNotIn("Band", captions._burned(cues, f, "16x9"))


if __name__ == "__main__":
    unittest.main()
