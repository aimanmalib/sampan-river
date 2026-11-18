"""Caption files from config: ASS colours, wrapping, timing, SRT, end card (offline, pure)."""
import json
import os
import unittest

from tools import captions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def film():
    with open(os.path.join(ROOT, "config", "film.json"), encoding="utf-8") as f:
        return json.load(f)


CUES = [{"start": 0.2, "end": 3.2, "text": "A short hook line.", "fact": None},
        {"start": 61.5, "end": 64.25, "text": "A much longer second caption that has to wrap onto two lines.", "fact": None}]


class CaptionsTest(unittest.TestCase):
    def test_colour_is_ass_bgr_with_alpha(self):
        self.assertEqual(captions.ass_colour("#FFF8E7"), "&H00E7F8FF")
        self.assertEqual(captions.ass_colour("#102030", 0x60), "&H60302010")
        with self.assertRaises(ValueError):
            captions.ass_colour("#FFF")

    def test_times(self):
        self.assertEqual(captions.ass_time(61.5), "0:01:01.50")
        self.assertEqual(captions.srt_time(64.25), "00:01:04,250")

    def test_wrap_balances_two_lines_within_width(self):
        lines = captions.wrap(CUES[1]["text"], 42)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(x) <= 42 for x in lines))
        self.assertLess(abs(len(lines[0]) - len(lines[1])), 12)
        self.assertEqual(" ".join(lines), CUES[1]["text"])

    def test_more_than_two_lines_is_refused(self):
        with self.assertRaises(ValueError):
            captions.caption_lines([{"start": 0, "end": 1, "text": "word " * 30}], 20)

    def test_ass_has_every_cue_at_its_time_with_config_style(self):
        f = film()
        text = captions.captions_ass(CUES, f, "16x9")
        self.assertIn(f"PlayResX: {f['output']['16x9']['width']}", text)
        self.assertIn(f"Caption,{f['captions']['font']},{f['captions']['size']['16x9']},", text)
        events = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
        self.assertEqual(len(events), 2)
        self.assertTrue(events[1].startswith("Dialogue: 0,0:01:01.50,0:01:04.25,Caption,"))
        self.assertIn("\\N", events[1])

    def test_srt_numbered_in_order(self):
        text = captions.srt(list(reversed(CUES)), 42)
        self.assertTrue(text.startswith("1\n00:00:00,200 --> 00:00:03,200\nA short hook line.\n\n2\n"))

    def test_end_card_lines_from_config_until_film_end(self):
        f = film()
        f["end_card"]["lines"] = ["Line one", "line two", "line three"]
        text = captions.endcard_ass(f, "9x16", 60.0)
        events = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
        self.assertEqual(len(events), 3)
        self.assertTrue(all(captions.ass_time(60.0) in e for e in events))
        ys = [int(e.split("\\pos(")[1].split(",")[1].split(")")[0]) for e in events]
        self.assertEqual(ys, sorted(ys))
        self.assertTrue(events[0].endswith("Line one"))

    def test_committed_cues_fit_both_versions(self):
        cues = captions.load(captions.CAPTIONS)["cues"]
        f = film()
        for v in ("16x9", "9x16"):
            for _, _, lines in captions.caption_lines(cues, f["captions"]["max_chars_per_line"][v]):
                self.assertLessEqual(len(lines), 2)

    def test_line_length_fits_frame_width(self):
        f = film()
        c = f["captions"]
        for v in ("16x9", "9x16"):
            usable = f["output"][v]["width"] * (1 - 2 * 0.06)
            self.assertLessEqual(c["max_chars_per_line"][v] * c["size"][v] * 0.6, usable, v)

    def test_end_card_lines_fit_frame_width(self):
        f = film()
        e = f["end_card"]
        for v in ("16x9", "9x16"):
            usable = f["output"][v]["width"] * (1 - 2 * 0.06)
            for i, line in enumerate(e["lines"]):
                size = e["size"][v][0 if i == 0 else 1]
                self.assertLessEqual(len(line) * size * 0.6, usable, f"{v}: {line}")


if __name__ == "__main__":
    unittest.main()
