"""The vertical short (decision 0008): segment plan, joins, captions and the derived film config (offline)."""
import copy
import json
import os
import re
import unittest

from tools import captions, short

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


FIXTURE = {"version": "short-9x16", "source": "9x16", "segments": [[0.0, 4.0], [10.0, 16.0], [50.0, 58.0]],
           "crossfade_s": 0.5, "audio_fade_out_s": 1.0, "duration_s": {"min": 15, "max": 20}, "hook_max_s": 3.0}


class ShortTest(unittest.TestCase):
    def setUp(self):
        self.film = load("config/film.json")
        self.short = copy.deepcopy(FIXTURE)

    def test_total_and_offsets_subtract_one_crossfade_per_join(self):
        self.assertEqual(short.total_s(self.short), 17.0)
        self.assertEqual(short.offsets(self.short), [3.5, 9.0])

    def test_check_refuses_segments_outside_the_film_or_out_of_order(self):
        for segs in ([[0.0, 4.0], [58.0, 61.0]], [[10.0, 16.0], [0.0, 4.0], [50.0, 58.0]], [[0.0, 0.8], [1.0, 19.0]]):
            self.short["segments"] = segs
            with self.assertRaises(short.ShortError):
                short.check(self.short, self.film)

    def test_check_refuses_a_short_outside_the_length_limits(self):
        self.short["segments"] = [[0.0, 4.0], [10.0, 16.0]]
        with self.assertRaisesRegex(short.ShortError, "outside 15..20"):
            short.check(self.short, self.film)
        self.short["segments"] = [[0.0, 10.0], [20.0, 34.0]]
        with self.assertRaises(short.ShortError):
            short.check(self.short, self.film)

    def test_cues_must_sit_inside_the_short_and_hook_early(self):
        short.check_cues(self.short, [{"start": 0.2, "end": 3.0, "text": "a"}])
        with self.assertRaisesRegex(short.ShortError, "first 3.0 s"):
            short.check_cues(self.short, [{"start": 3.5, "end": 5.0, "text": "a"}])
        with self.assertRaisesRegex(short.ShortError, "outside the short"):
            short.check_cues(self.short, [{"start": 0.2, "end": 17.5, "text": "a"}])

    def test_video_and_audio_joins_use_the_same_crossfade_and_offsets(self):
        v = short.video_graph(self.short, 24)
        self.assertEqual(re.findall(r"xfade=transition=fade:duration=0.5:offset=([\d.]+)", v), ["3.5", "9.0"])
        self.assertTrue(v.endswith("[out]"))
        a = short.audio_graph(self.short, short.total_s(self.short))
        self.assertEqual(a.count("acrossfade=d=0.5"), 2)
        self.assertIn("afade=t=out:st=16.0:d=1.0[out]", a)

    def test_commands_cut_each_segment_from_the_source(self):
        cmd = short.clean_cmd(self.short, self.film, "clean-9x16.mp4", "out.mp4")
        self.assertEqual([cmd[i + 1] for i, x in enumerate(cmd) if x == "-ss"], ["0.000", "10.000", "50.000"])
        self.assertEqual([cmd[i + 1] for i, x in enumerate(cmd) if x == "-t"], ["4.000", "6.000", "8.000"])
        m = short.mix_cmd(self.short, self.film, "mix.wav", "out.wav")
        self.assertEqual(m.count("mix.wav"), 3)

    def test_short_film_takes_the_source_style_and_the_short_length(self):
        sf = short.short_film(self.film, self.short)
        self.assertEqual(sf["output"]["short-9x16"], self.film["output"]["9x16"])
        self.assertEqual(sf["captions"]["margin_v"]["short-9x16"], self.film["captions"]["margin_v"]["9x16"])
        self.assertEqual(sf["measure"]["caption_band"]["short-9x16"], self.film["measure"]["caption_band"]["9x16"])
        self.assertEqual(sf["duration_s"], {"min": 15, "max": 20, "target": 17.0, "hook_max_s": 3.0})
        self.assertEqual(sf["edit"]["layout"]["short-9x16"], self.film["edit"]["layout"]["9x16"])
        self.assertEqual(sf["captions"]["bands"]["short-9x16"], self.film["captions"]["bands"]["9x16"])
        self.assertNotIn("short-9x16", self.film["output"])
        self.assertNotIn("short-9x16", self.film["captions"]["bands"])

    def test_film_seconds_map_to_short_seconds(self):
        # segments [0, 4] [10, 16] [50, 58], crossfade 0.5: second segment starts at 3.5, third at 9.0
        self.assertEqual(short.to_short(self.short, 2.0), 2.0)
        self.assertEqual(short.to_short(self.short, 12.0), 5.5)
        self.assertEqual(short.to_short(self.short, 50.0), 9.0)
        self.assertEqual(short.to_short(self.short, 30.0), 9.0)  # in a gap: start of the next segment
        self.assertEqual(short.to_short(self.short, 59.0), short.total_s(self.short))

    def test_end_card_starts_in_short_seconds(self):
        sf = short.short_film(self.film, self.short)
        self.assertEqual(sf["end_card"]["start_s"], short.to_short(self.short, self.film["end_card"]["start_s"]))
        self.assertEqual(self.film["end_card"]["start_s"], load("config/film.json")["end_card"]["start_s"])

    def test_committed_short_bands_fit_and_are_sourced(self):
        from tools import bands
        sh, cues = load("config/short.json"), load("config/captions.short.en.json")["cues"]
        sf, rows = short.short_film(self.film, sh), bands.rows_for(sh["version"])
        with open(os.path.join(ROOT, "docs", "FACTS.md"), encoding="utf-8") as f:
            facts = f.read()
        self.assertEqual(bands.check_layout(sf, sh["version"], cues, rows), [])
        self.assertEqual(bands.check_figures(rows, cues, facts, sf), [])
        spans, card = bands.intervals(sf, sh["version"], cues, rows), sf["end_card"]["start_s"]
        for band in ("top", "bottom"):
            self.assertGreaterEqual(bands.cover(spans[band], card), sf["measure"]["band_cover_min"])
        late = copy.deepcopy(rows)
        late[-1]["end"] = card + 1.0
        self.assertTrue(bands.check_figures(late, cues, facts, sf))
        burned = captions._burned(cues, sf, sh["version"])
        self.assertIn("BandFigure", burned)

    def test_committed_short_fits_the_plan(self):
        sh, cues = load("config/short.json"), load("config/captions.short.en.json")["cues"]
        t = short.check(sh, self.film)
        short.check_cues(sh, cues)
        self.assertTrue(15 <= t <= 20)
        self.assertGreaterEqual(sh["crossfade_s"], 0.3)
        self.assertLessEqual(len(cues), 4)
        with open(os.path.join(ROOT, "docs", "FACTS.md"), encoding="utf-8") as f:
            facts = f.read()
        for c in cues:
            if c.get("fact"):
                self.assertIn(f"`{c['fact']}`", facts)
        self.assertIsNone(cues[0]["fact"])
        self.assertLess(cues[0]["start"], 3.0)


if __name__ == "__main__":
    unittest.main()
