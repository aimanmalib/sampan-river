"""Vertical share image (decision 0014): layout, committed images and the preview tags in the built page.

Offline: ffmpeg is not run; the build uses the fixture repository of test_site (fake media with their own sha256).
"""
import copy
import json
import os
import re
import unittest

from tests import test_site
from tools import og, site

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


SITE = load("config/site.json")
OG = SITE["og_build"]
TEXT = {"title": "Title", "hook": ["A hook line", "second line"], "figure": "9 x", "label": "a label",
        "domain": "example.test"}


class LayoutTest(unittest.TestCase):
    def test_repository_layout_keeps_hook_picture_and_figure_inside_the_crops(self):
        text = og.words(OG, load("config/film.json"), load("config/captions.en.json"), load("config/bands.json"),
                        SITE["domain"])
        self.assertEqual(og.check_layout(OG, text), [])

    def test_words_come_from_the_film(self):
        text = og.words(OG, load("config/film.json"), load("config/captions.en.json"), load("config/bands.json"),
                        SITE["domain"])
        cue = next(c for c in load("config/captions.en.json")["cues"] if c["id"] == OG["hook_caption"])
        band = next(b for b in load("config/bands.json")["9x16"] if b.get("fact") == OG["figure_fact"])
        self.assertEqual(" ".join(text["hook"]), cue["text"])
        self.assertEqual((text["figure"], text["label"]), (band["figure"], band["label"]))
        self.assertEqual(text["title"], load("config/film.json")["title"])

    def test_unknown_caption_or_fact_is_refused(self):
        film, caps, bands = load("config/film.json"), load("config/captions.en.json"), load("config/bands.json")
        with self.assertRaises(og.OgError):
            og.words(dict(OG, hook_caption="nope"), film, caps, bands, "d")
        with self.assertRaises(og.OgError):
            og.words(dict(OG, figure_fact="nope"), film, caps, bands, "d")

    def test_picture_pushed_out_of_the_wide_crop_is_reported(self):
        bad = copy.deepcopy(OG)
        bad["picture"]["y"] += 40
        self.assertTrue(any("picture" in p for p in og.check_layout(bad, TEXT)))

    def test_hook_above_the_wide_crop_is_reported(self):
        bad = copy.deepcopy(OG)
        bad["hook"]["y"] = 100
        self.assertTrue(any("hook" in p for p in og.check_layout(bad, TEXT)))

    def test_title_above_the_wide_crop_is_reported(self):
        # The first K2 layout: title at y 168, only inside the 1:1 box, so a 1.91:1 preview lost it.
        bad = copy.deepcopy(OG)
        bad["title"] = {"y": 168, "size": 96}
        self.assertTrue(any("title" in p for p in og.check_layout(bad, TEXT)))

    def test_title_on_the_hook_is_reported(self):
        bad = copy.deepcopy(OG)
        bad["title"]["y"] = bad["hook"]["y"] - bad["title"]["size"] // 2
        self.assertTrue(any("title" in p for p in og.check_layout(bad, TEXT)))

    def test_command_scales_with_lanczos_and_draws_text_with_ass(self):
        cmd = og.og_cmd(OG, "frame.jpg", "og.ass", "out.jpg")
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("flags=lanczos", graph)
        self.assertIn("ass=og.ass", graph)

    def test_ass_has_every_line(self):
        ass = og.og_ass(OG, TEXT, load("config/film.json")["captions"])
        for line in ("Title", "A hook line", "second line", "9 x", "a label", "example.test"):
            self.assertIn("," + line + "\n", ass.replace("}", ","))


def jpeg(rel):
    path = os.path.join(ROOT, rel)
    with open(path, "rb") as f:
        head = f.read(3)
    return path, head, site.jpeg_size(path)


class CommittedImageTest(unittest.TestCase):
    def test_share_image_is_a_vertical_jpeg_under_the_limits(self):
        path, head, (w, h) = jpeg(SITE["og_image"])
        self.assertEqual(head, b"\xff\xd8\xff")
        self.assertGreater(h, w)
        self.assertEqual((w, h), (OG["width"], OG["height"]))
        self.assertLessEqual(os.path.getsize(path), min(SITE["og_image_max_bytes"], OG["max_bytes"]))
        self.assertEqual(SITE["og_image"], OG["out"])

    def test_crops_are_committed_small_and_shaped_like_the_previews(self):
        for name, crop in OG["crops"].items():
            path, head, (w, h) = jpeg(crop["out"])
            self.assertEqual(head, b"\xff\xd8\xff")
            self.assertLessEqual(os.path.getsize(path), OG["crop_max_bytes"])
            self.assertAlmostEqual(w / h, OG["width"] / crop["height"], places=2, msg=name)

    def test_x_keeps_the_landscape_thumbnail(self):
        _, _, (w, h) = jpeg(SITE["twitter_image"])
        self.assertGreater(w, h)


class PreviewTagsTest(unittest.TestCase):
    tearDown = test_site.SiteBuildTest.tearDown
    write_measured = test_site.SiteBuildTest.write_measured
    write_cfg = test_site.SiteBuildTest.write_cfg
    page = test_site.SiteBuildTest.page

    def setUp(self):
        test_site.SiteBuildTest.setUp(self)
        self.write_cfg()

    def meta(self, html, prop):
        m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(prop), html)
        self.assertIsNotNone(m, prop)
        return m.group(1)

    def test_preview_tags_are_absolute_and_name_the_vertical_film(self):
        site.build(self.root, self.media, self.out)
        base = "https://" + self.cfg["domain"]
        for rel in ("index.html", "ms/index.html"):
            html = self.page(rel)
            for prop in ("og:image", "twitter:image", "og:video", "og:video:secure_url"):
                self.assertTrue(self.meta(html, prop).startswith(base + "/"), prop)
            self.assertEqual((self.meta(html, "og:image:width"), self.meta(html, "og:image:height")), ("36", "64"))
            first_player = re.search(r'<source src="([^"]+)"', html).group(1)
            vertical = self.meta(html, "og:video")
            self.assertTrue(vertical.endswith("/" + self.cfg["videos"]["vertical"]["file"]))
            self.assertEqual(vertical, base + first_player)
            self.assertEqual(self.meta(html, "og:video:type"), "video/mp4")
            self.assertEqual(self.meta(html, "og:video:height"), str(self.cfg["videos"]["vertical"]["height"]))
            self.assertTrue(self.meta(html, "og:image:alt"))
            self.assertTrue(self.meta(html, "twitter:image:alt"))
        self.assertNotEqual(self.meta(self.page("index.html"), "og:image:alt"),
                            self.meta(self.page("ms/index.html"), "og:image:alt"))

    def test_landscape_share_image_stops_the_build(self):
        with open(os.path.join(self.root, self.cfg["og_image"]), "wb") as f:
            f.write(test_site.FAKE_JPEG)
        with self.assertRaisesRegex(site.BuildError, "not vertical"):
            site.build(self.root, self.media, self.out)

    def test_landscape_thumbnail_is_the_config_way_back(self):
        self.write_cfg(og_image=self.cfg["twitter_image"], og_image_portrait=False)
        site.build(self.root, self.media, self.out)
        self.assertIn('og:image:height" content="36"', self.page("index.html"))


if __name__ == "__main__":
    unittest.main()
