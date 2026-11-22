"""Watch on YouTube beside Share and a repository link without JavaScript (decision 0017), offline on fixtures."""
import importlib.util
import os
import re
import unittest

from tests import test_share, test_site
from tools import site

ROOT = test_site.ROOT
URL = "https://youtu.be/fixture"


def load_check_page():
    spec = importlib.util.spec_from_file_location("check_page", os.path.join(ROOT, "deploy", "check_page.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WatchBuildTest(unittest.TestCase):
    setUp = test_site.SiteBuildTest.setUp
    tearDown = test_site.SiteBuildTest.tearDown
    write_measured = test_site.SiteBuildTest.write_measured
    write_cfg = test_site.SiteBuildTest.write_cfg
    page = test_site.SiteBuildTest.page
    lang = test_share.ShareBuildTest.lang
    pages = test_share.ShareBuildTest.pages

    def actions(self, html):
        m = re.search(r'<div class="actions">(.*?)\n    </div>\n', html, re.S)
        return m.group(1) if m else ""

    def test_one_watch_link_beside_share_in_both_languages(self):
        self.write_cfg(youtube_url=URL)
        site.build(self.root, self.media, self.out)
        for path, html in self.pages().items():
            self.assertEqual(html.count("youtu.be"), 1, path)
            row = self.actions(html)
            self.assertIn(f'<a class="watch" data-watch href="{URL}" rel="noopener">', row, path)
            self.assertIn("data-share", row, path)
            self.assertLess(row.index("data-watch"), row.index("data-share"), path)
        self.assertIn(">Watch on YouTube</a>", self.pages()["/"])
        self.assertIn(">Tonton di YouTube</a>", self.pages()["/ms/"])

    def test_no_watch_link_without_a_youtube_url(self):
        self.write_cfg(youtube_url="")
        site.build(self.root, self.media, self.out)
        for path, html in self.pages().items():
            self.assertNotIn("data-watch", html, path)
            self.assertIn("data-share", self.actions(html), path)

    def test_watch_link_stays_when_share_is_off(self):
        self.write_cfg(youtube_url=URL, share=dict(self.cfg["share"], enabled=False))
        site.build(self.root, self.media, self.out)
        for path, html in self.pages().items():
            self.assertIn("data-watch", self.actions(html), path)
            self.assertNotIn("data-share", html, path)

    def test_no_empty_row_when_both_are_off(self):
        self.write_cfg(youtube_url="", share=dict(self.cfg["share"], enabled=False))
        site.build(self.root, self.media, self.out)
        self.assertNotIn('class="actions"', self.page("index.html"))

    def test_repository_link_is_plain_html_when_on(self):
        self.write_cfg(banner=dict(self.cfg["banner"], repo_check="on"))
        site.build(self.root, self.media, self.out)
        repo = re.escape(self.cfg["repo_url"])
        for path, html in self.pages().items():
            tags = re.findall(rf'<a href="{repo}[^"]*"[^>]*>', html)
            self.assertGreaterEqual(len(tags), 2, path)
            for tag in tags:
                self.assertNotIn("hidden", tag, path)
            self.assertNotIn("repo.js", html, path)
            self.assertNotIn("data-repo-api", html, path)


class NestedBlockTest(unittest.TestCase):
    def test_inner_blocks_follow_their_own_flag(self):
        t = "<!--if:a-->\n[<!--if:b-->\nB\n<!--end:b-->\n<!--if:c-->\nC\n<!--end:c-->\n]\n<!--end:a-->\n"
        self.assertEqual(site.render(t, {}, {}, {"a": True, "b": True, "c": False}), "[B\n]\n")
        self.assertEqual(site.render(t, {}, {}, {"a": False, "b": True, "c": True}), "")


class WatchProblemsTest(unittest.TestCase):
    """deploy/check_page.py Watch and repository link decisions, without a browser."""

    CFG = {"youtube_url": URL, "repo_url": "https://github.com/o/r", "banner": {"repo_check": "on"}}

    def setUp(self):
        self.cp = load_check_page()

    def probe(self, **kw):
        p = {"viewport": 664, "youtubeLinks": 1, "shownLinks": ["https://github.com/o/r"],
             "watch": {"top": 560, "bottom": 608, "h": 48, "w": 180, "href": URL,
                       "color": "rgb(27, 26, 23)", "bg": "rgb(255, 248, 231)"}}
        p.update(kw)
        return p

    def watch(self, **kw):
        return dict(self.probe()["watch"], **kw)

    def test_complete_page_passes(self):
        for mode in ("iphone", "phone", "desktop"):
            self.assertEqual(self.cp.watch_problems(self.probe(), self.CFG, mode), [], mode)

    def test_each_fault_is_named(self):
        cases = {"is not shown": dict(watch=None),
                 "2 YouTube links": dict(youtubeLinks=2),
                 "points to https://youtu.be/other": dict(watch=self.watch(href="https://youtu.be/other")),
                 "smaller than 44": dict(watch=self.watch(h=30)),
                 "contrast": dict(watch=self.watch(color="rgb(200, 190, 170)")),
                 "contrast 0.0": dict(watch=self.watch(bg="rgba(0, 0, 0, 0)")),
                 "below the first screen": dict(watch=self.watch(top=640, bottom=688)),
                 "repository link is not shown": dict(shownLinks=[])}
        for needle, kw in cases.items():
            problems = self.cp.watch_problems(self.probe(**kw), self.CFG, "iphone")
            self.assertTrue(any(needle in x for x in problems), (needle, problems))

    def test_below_the_fold_only_matters_on_the_iphone(self):
        p = self.probe(watch=self.watch(top=900, bottom=948))
        self.assertEqual(self.cp.watch_problems(p, self.CFG, "phone"), [])

    def test_no_youtube_url_wants_no_youtube_link(self):
        cfg = dict(self.CFG, youtube_url="")
        self.assertEqual(self.cp.watch_problems(self.probe(watch=None, youtubeLinks=0), cfg, "iphone"), [])
        self.assertTrue(self.cp.watch_problems(self.probe(watch=None), cfg, "iphone"))

    def test_hidden_repository_link_is_fine_when_auto(self):
        cfg = dict(self.CFG, banner={"repo_check": "auto"})
        self.assertEqual(self.cp.watch_problems(self.probe(shownLinks=[]), cfg, "iphone"), [])


if __name__ == "__main__":
    unittest.main()
