"""Thumbnail source frame, text layout and ffmpeg command (offline; ffmpeg is not run)."""
import copy
import json
import os
import unittest

from tools import thumb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMB = {"shot": "a", "orientation": "landscape", "clip_s": 10.0, "width": 1280, "height": 720, "scale": "lanczos",
         "lines": ["Title", "A second line"], "font": "DejaVu Sans", "size": [92, 44], "line_gap_px": 14,
         "colour": "#FFF8E7", "outline_colour": "#1B1A17", "outline_px": 5, "margin_right_px": 56,
         "margin_top_px": 44, "jpeg_qscale": 2, "max_bytes": 2000000, "out": "media/edit/t.jpg"}
SHOTS = {"shots": [{"id": "a", "window_s": [4.0, 22.0], "accepted": {"landscape": "a-L1.mp4"}},
                   {"id": "b", "window_s": [0.0, 5.0], "accepted": {}}]}


class ThumbTest(unittest.TestCase):
    def test_source_is_accepted_clip_inside_window(self):
        self.assertEqual(thumb.source(THUMB, SHOTS), ("a-L1.mp4", 10.0))

    def test_source_refuses_second_outside_window(self):
        for t in (3.9, 22.1):
            with self.assertRaises(thumb.ThumbError):
                thumb.source(dict(THUMB, clip_s=t), SHOTS)

    def test_source_refuses_unknown_shot_or_missing_clip(self):
        with self.assertRaises(thumb.ThumbError):
            thumb.source(dict(THUMB, shot="zz"), SHOTS)
        with self.assertRaises(thumb.ThumbError):
            thumb.source(dict(THUMB, shot="b", clip_s=1.0), SHOTS)

    def test_ass_has_every_line_top_right(self):
        ass = thumb.thumb_ass(THUMB)
        self.assertIn("PlayResX: 1280", ass)
        self.assertIn("{\\pos(1224,44)}Title", ass)
        self.assertIn("{\\pos(1224,150)}A second line", ass)
        styles = [l for l in ass.splitlines() if l.startswith("Style:")]
        self.assertTrue(all(s.split(",")[18] == "9" for s in styles))

    def test_ass_refuses_text_below_frame(self):
        t = copy.deepcopy(THUMB)
        t["lines"] = ["x"] * 20
        with self.assertRaises(thumb.ThumbError):
            thumb.thumb_ass(t)

    def test_command_takes_one_frame_with_lanczos(self):
        cmd = thumb.thumb_cmd(THUMB, "clips/a-L1.mp4", 10.0, "thumb.ass", "out.jpg")
        self.assertEqual(cmd[cmd.index("-ss") + 1], "10.000")
        self.assertEqual(cmd[cmd.index("-frames:v") + 1], "1")
        self.assertEqual(cmd[cmd.index("-vf") + 1], "scale=1280:720:flags=lanczos,ass=thumb.ass")
        self.assertEqual(cmd[-1], "out.jpg")

    def test_config_thumbnail_is_valid(self):
        with open(os.path.join(ROOT, "config", "film.json"), encoding="utf-8") as f:
            cfg = json.load(f)["thumbnail"]
        with open(os.path.join(ROOT, "config", "shots.json"), encoding="utf-8") as f:
            shots = json.load(f)
        thumb.source(cfg, shots)
        thumb.thumb_ass(cfg)
        self.assertEqual(cfg["scale"], "lanczos")
        self.assertLessEqual(cfg["max_bytes"], 2000000)


if __name__ == "__main__":
    unittest.main()
