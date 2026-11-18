"""Frame layouts (offline; ffmpeg is not run)."""
import json
import os
import re
import unittest

from tools import layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIP = "a.mp4"


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.film = load("config/film.json")
        lay = self.film["edit"]["layout"]["9x16"]
        lay.update({"mode": "blur_fill", "crop_aspect": [1, 1], "picture_y_ratio": 0.5,
                    "centre_x": {CLIP: [[0, 400], [10, 900], [20, 900]]}})

    def crop(self):
        self.film["edit"]["layout"]["9x16"]["mode"] = "crop_fill"
        return self.film["output"]["9x16"]

    def test_cover_layout_scales_to_frame(self):
        g = layout.segment_graph(self.film, "16x9", 1)
        o = self.film["output"]["16x9"]
        self.assertEqual(g, f"[1:v]scale={o['width']}:{o['height']}:flags={o['scale']},setsar=1,fps=24,format=yuv420p[v1]")
        self.assertEqual(layout.picture_box(self.film, "16x9"), (0, 0, o["width"], o["height"]))

    def test_blur_fill_keeps_full_picture_and_aspect(self):
        o = self.film["output"]["9x16"]
        x, y, w, h = layout.picture_box(self.film, "9x16")
        sw, sh = layout.source_size(self.film, "9x16")
        self.assertEqual((x, w), (0, o["width"]))
        self.assertLessEqual(abs(w / h - sw / sh), 0.01)
        self.assertTrue(0 <= y and y + h <= o["height"])
        self.assertEqual((w % 2, h % 2, y % 2), (0, 0, 0))
        g = layout.segment_graph(self.film, "9x16", 0, CLIP)
        self.assertIn(f"[f0]scale={w}:{h}:flags={o['scale']}[fg0]", g)
        self.assertIn(f"overlay=0:{y}", g)
        self.assertIn("boxblur=", g)
        self.assertTrue(g.endswith("format=yuv420p[v0]"))

    def test_crop_fill_box_size_and_graph(self):
        o = self.crop()
        sw, sh = layout.source_size(self.film, "9x16")
        self.assertEqual(layout.crop_size(self.film, "9x16"), (sh, sh))
        self.assertEqual(layout.crop_size(self.film, "9x16", [4, 5]), (int(round(sh * 0.8 / 2)) * 2, sh))
        x, y, w, h = layout.picture_box(self.film, "9x16")
        self.assertEqual((x, w, h), (0, o["width"], o["width"]))
        g = layout.segment_graph(self.film, "9x16", 2, CLIP)
        self.assertIn(f"[f2]crop={sh}:{sh}:'", g)
        self.assertIn(f":0,scale={w}:{h}:flags={o['scale']}[fg2]", g)
        self.assertIn(f"overlay=0:{y}", g)
        self.assertIn("boxblur=", g)

    def test_crop_x_follows_keyframes(self):
        self.crop()
        keys = layout.keyframes(self.film, "9x16", CLIP)
        self.assertEqual(keys, [(0.0, 40), (10.0, 540), (20.0, 540)])
        self.assertEqual(layout.left_at(keys, 0), 40)
        self.assertEqual(layout.left_at(keys, 5), 290)
        self.assertEqual(layout.left_at(keys, 25), 540)
        expr = layout.x_expr(keys).replace("\\,", ",")
        for t in (0, 2.5, 5, 9.9, 10, 15, 30):
            self.assertAlmostEqual(self.eval_expr(expr, t), layout.left_at(keys, t), places=6)

    @staticmethod
    def eval_expr(expr, t):
        """Evaluate the nested if(lt(t,a),b,c) expression the way ffmpeg does."""
        def ev(s):
            s = s.strip()
            if s.startswith("if(lt(t,"):
                body = s[len("if("):-1]
                parts, depth, cur = [], 0, ""
                for ch in body:
                    if ch == "," and depth == 0:
                        parts.append(cur)
                        cur = ""
                        continue
                    depth += ch == "("
                    depth -= ch == ")"
                    cur += ch
                parts.append(cur)
                cond = float(parts[0][len("lt(t,"):-1])
                return ev(parts[1]) if t < cond else ev(parts[2])
            return eval(s, {"__builtins__": {}, "t": t})  # noqa: S307 digits, t and + - * / only
        return ev(expr)

    def test_crop_box_outside_the_frame_is_an_error(self):
        self.crop()
        sw, sh = layout.source_size(self.film, "9x16")
        for bad in (sh / 2 - 1, sw - sh / 2 + 1):
            self.film["edit"]["layout"]["9x16"]["centre_x"][CLIP] = [[0, 640], [5, bad]]
            with self.assertRaises(layout.LayoutError):
                layout.segment_graph(self.film, "9x16", 0, CLIP)

    def test_keyframes_must_start_at_zero_and_rise(self):
        self.crop()
        for keys in ([[1, 640]], [[0, 640], [5, 640], [5, 700]], []):
            self.film["edit"]["layout"]["9x16"]["centre_x"][CLIP] = keys
            with self.assertRaises(layout.LayoutError):
                layout.keyframes(self.film, "9x16", CLIP)

    def test_committed_picture_stays_clear_of_caption_band_and_safe_area(self):
        film = load("config/film.json")
        _, y, _, h = layout.picture_box(film, "9x16")
        height = film["output"]["9x16"]["height"]
        band = film["measure"]["caption_band"]["9x16"]
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(y + h, band[0] * height)
        self.assertLessEqual(band[1], 1 - film["captions"]["safe_bottom_ratio"]["9x16"])

    def test_committed_keyframes_valid_for_every_9x16_clip(self):
        film = load("config/film.json")
        shots = load("config/shots.json")["shots"]
        for s in shots:
            layout.keyframes(film, "9x16", s["accepted"]["landscape"])

    def test_unknown_layout_refused(self):
        self.film["edit"]["layout"]["9x16"]["mode"] = "stretch"
        with self.assertRaises(layout.LayoutError):
            layout.segment_graph(self.film, "9x16", 0)


if __name__ == "__main__":
    unittest.main()
