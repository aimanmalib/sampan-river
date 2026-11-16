"""Edit plan and ffmpeg command shape (offline; ffmpeg is not run)."""
import copy
import json
import os
import unittest

from tools import edit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


SHOTS = {"shots": [
    {"id": "b", "window_s": [8.0, 22.0], "film_s": [40.0, 54.0], "accepted": {"landscape": "b.mp4"}},
    {"id": "a", "window_s": [5.0, 45.0], "film_s": [0.0, 40.0], "accepted": {"landscape": "a.mp4"}},
]}


class EditTest(unittest.TestCase):
    def setUp(self):
        self.film = load("config/film.json")
        self.film["end_card"]["start_s"] = 54.0
        self.film["duration_s"]["target"] = 60

    def test_plan_orders_shots_and_ends_at_end_card(self):
        segs = edit.plan(self.film, SHOTS, "16x9")
        self.assertEqual([s[0] for s in segs], ["a.mp4", "b.mp4"])

    def test_plan_refuses_gap_or_wrong_end(self):
        gap = copy.deepcopy(SHOTS)
        gap["shots"][0]["film_s"], gap["shots"][0]["window_s"] = [41.0, 54.0], [8.0, 21.0]
        with self.assertRaises(edit.EditError):
            edit.plan(self.film, gap, "16x9")
        self.film["end_card"]["start_s"] = 55.0
        with self.assertRaises(edit.EditError):
            edit.plan(self.film, SHOTS, "16x9")

    def test_plan_refuses_missing_orientation(self):
        with self.assertRaises(edit.EditError):
            edit.plan(self.film, SHOTS, "9x16")

    def test_clean_command_cuts_windows_and_scales_with_config(self):
        segs = edit.plan(self.film, SHOTS, "16x9")
        cmd = edit.clean_cmd(self.film, segs, "16x9", "/clips", "/out/clean.mp4", "endcard-16x9.ass")
        self.assertEqual(cmd[cmd.index("/clips/a.mp4") - 5:cmd.index("/clips/a.mp4")], ["-ss", "5.000", "-t", "40.000", "-i"])
        graph = cmd[cmd.index("-filter_complex") + 1]
        o = self.film["output"]["16x9"]
        self.assertIn(f"scale={o['width']}:{o['height']}:flags={o['scale']}", graph)
        self.assertIn("concat=n=2", graph)
        self.assertIn("stop_duration=6.0", graph)
        self.assertIn("ass=endcard-16x9.ass", graph)
        self.assertIn("trim=duration=60.0", graph)
        self.assertIn("-an", cmd)

    def test_loudnorm_targets_come_from_config(self):
        a = self.film["audio"]
        tp = a["true_peak_max_db"] - self.film["edit"]["loudnorm"]["true_peak_margin_db"]
        self.assertTrue(edit.loudnorm_target(self.film).startswith(f"I={a['lufs_target']}:TP={tp}:"))
        self.assertLess(tp, a["true_peak_max_db"])

    def test_parse_loudnorm_and_second_pass(self):
        stderr = ('[Parsed_loudnorm_0 @ 0x1]\n{\n\t"input_i" : "-14.60",\n\t"input_tp" : "-2.10",\n\t"input_lra" : "5.0",\n'
                  '\t"input_thresh" : "-25.0",\n\t"target_offset" : "0.1"\n}\n')
        m = edit.parse_loudnorm(stderr)
        f = edit.second_pass(self.film, m)
        self.assertIn("measured_I=-14.60", f)
        self.assertIn("offset=0.1", f)
        self.assertTrue(f.endswith("linear=true"))
        with self.assertRaises(edit.EditError):
            edit.parse_loudnorm("no json here")

    def test_final_command_is_h264_high_aac_faststart(self):
        cmd = edit.final_cmd(self.film, "c.mp4", "m.wav", "captions-16x9.ass", "loudnorm=I=-14", "o.mp4")
        for a, b in (("-c:v", "libx264"), ("-profile:v", "high"), ("-pix_fmt", "yuv420p"), ("-c:a", "aac"),
                     ("-movflags", "+faststart"), ("-ac", "2"), ("-ar", "48000")):
            self.assertEqual(cmd[cmd.index(a) + 1], b)
        self.assertIn("[0:v]ass=captions-16x9.ass[v]", cmd[cmd.index("-filter_complex") + 1])

    def test_committed_shots_tile_the_landscape_film(self):
        segs = edit.plan(load("config/film.json"), load("config/shots.json"), "16x9")
        self.assertGreaterEqual(len(segs), 3)


if __name__ == "__main__":
    unittest.main()
