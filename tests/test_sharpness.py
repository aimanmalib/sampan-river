"""9:16 layout sharpness (offline: the frame reader is a fake, ffmpeg is not run)."""
import json
import os
import unittest

import numpy as np

from tools import sharpness

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = {"shots": [{"id": "a", "window_s": [2.0, 12.0], "film_s": [0.0, 10.0], "accepted": {"landscape": "a.mp4"}}]}


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def fake_luma(scale_softness):
    """A checkerboard whose contrast falls with the display scale, so bigger = softer per pixel."""
    def luma(path, t, left, rw, rh, scale, flags):
        h, w = 40, 40
        board = (np.indices((h, w)).sum(axis=0) % 2) * 100.0
        return (board / scale ** scale_softness).astype(np.uint8)
    return luma


class SharpnessTest(unittest.TestCase):
    def setUp(self):
        self.film = load("config/film.json")
        lay = self.film["edit"]["layout"]["9x16"]
        lay["centre_x"] = {"a.mp4": [[0, 640], [10, 700]]}
        self.film["measure"]["sharpness"].update({"sample_fracs": [0.25, 0.75], "region_aspect": [4, 5],
                                                  "aspects": {"4:5": [4, 5], "1:1": [1, 1]}, "min_ratio": 0.55})

    def test_laplacian_variance(self):
        self.assertEqual(sharpness.laplacian_var(np.full((8, 8), 50, np.uint8)), 0.0)
        board = (np.indices((8, 8)).sum(axis=0) % 2) * 10
        self.assertGreater(sharpness.laplacian_var(board), 0)

    def test_samples_follow_window_and_keyframes(self):
        s = sharpness.samples(self.film, SHOTS)
        self.assertEqual([(c, t, rel) for c, t, rel, _ in s], [("a.mp4", 4.5, 2.5), ("a.mp4", 9.5, 7.5)])
        rw = self.film["ve"]["resolution"]["landscape"].split("x")
        self.assertEqual(s[0][3], round(640 + 60 * 0.25 - 576 / 2))
        self.assertTrue(all(0 <= left <= int(rw[0]) - 576 for *_, left in s))

    def test_soft_crops_keep_blur_fill(self):
        r = sharpness.measure(self.film, SHOTS, "clips", luma=fake_luma(4))
        self.assertIsNone(r["chosen"])
        self.assertEqual(r["passing"], [])
        self.assertLess(r["ratios"]["1:1"], 0.55)
        self.assertIn("Chosen: blur_fill (no crop passes)", sharpness.table(r, self.film))

    def test_largest_passing_picture_is_chosen(self):
        r = sharpness.measure(self.film, SHOTS, "clips", luma=fake_luma(0))
        self.assertEqual(r["passing"], ["4:5", "1:1"])
        self.assertEqual(r["chosen"], "4:5")
        self.film["measure"]["sharpness"]["min_ratio"] = 2.0
        self.assertIsNone(sharpness.summarise(r["rows"], self.film)["chosen"])

    def test_table_replaces_its_block_only(self):
        r = sharpness.measure(self.film, SHOTS, "clips", luma=fake_luma(4))
        md = sharpness.upsert("# M\n\nkeep\n", sharpness.table(r, self.film))
        again = sharpness.upsert(md, sharpness.table(r, self.film))
        self.assertEqual(md, again)
        self.assertTrue(again.startswith("# M\n\nkeep\n"))
        self.assertEqual(again.count("<!-- sharpness -->"), 1)


if __name__ == "__main__":
    unittest.main()
