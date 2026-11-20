"""Banner: new project note, first commit and repository links, deck link (decision 0015), offline on fixtures."""
import os
import re
import unittest

from tests import test_share, test_site
from tools import banner, site

ROOT = test_site.ROOT


class BannerBuildTest(unittest.TestCase):
    tearDown = test_site.SiteBuildTest.tearDown
    write_measured = test_site.SiteBuildTest.write_measured
    write_cfg = test_site.SiteBuildTest.write_cfg
    page = test_site.SiteBuildTest.page
    lang = test_share.ShareBuildTest.lang
    pages = test_share.ShareBuildTest.pages

    def setUp(self):
        test_site.SiteBuildTest.setUp(self)
        # The repository link tests start without a deck; the deck tests set one (the real deck: tests/test_deck.py).
        self.cfg["banner"] = dict(self.cfg["banner"], deck={"en": "", "ms": ""})
        self.write_cfg()

    def set_banner(self, **changes):
        self.write_cfg(banner=dict(self.cfg["banner"], **changes))

    def head(self, html):
        return re.search(r'<header class="banner".*?</header>', html, re.S).group(0)

    def test_first_commit_is_after_the_event_start(self):
        b = self.cfg["banner"]
        self.assertGreater(banner.parse_utc(b["first_commit"]["date_utc"]), banner.parse_utc(b["event_start_utc"]))
        self.assertEqual(banner.problems(self.cfg), [])

    def test_first_commit_before_the_start_stops_the_build(self):
        self.set_banner(first_commit=dict(self.cfg["banner"]["first_commit"], date_utc="2026-11-13T09:00:00Z"))
        with self.assertRaisesRegex(site.BuildError, "is not after the event start"):
            site.build(self.root, self.media, self.out)

    def test_note_in_both_languages_with_dates_from_config(self):
        site.build(self.root, self.media, self.out)
        pages = self.pages()
        self.assertIn("New project. First commit on 16 November 2026, after the 14 November start.", self.head(pages["/"]))
        ms = self.head(pages["/ms/"])
        self.assertIn('class="banner-note">Projek baharu.', ms)
        self.assertIn("16 November 2026", ms)
        self.assertNotIn("New project", ms)

    def test_note_follows_the_config_dates(self):
        self.set_banner(event_start_utc="2026-03-02T00:00:00Z",
                        first_commit=dict(self.cfg["banner"]["first_commit"], date_utc="2026-08-05T10:00:00Z"))
        site.build(self.root, self.media, self.out)
        pages = self.pages()
        self.assertIn("First commit on 5 August 2026, after the 2 March start.", pages["/"])
        self.assertIn("5 Ogos 2026", pages["/ms/"])
        self.assertIn("2 Mac", pages["/ms/"])

    def test_note_without_its_date_slot_stops_the_build(self):
        self.lang("en", lambda c: c["banner"].update(note="New project."))
        with self.assertRaisesRegex(site.BuildError, "banner.note has no"):
            site.build(self.root, self.media, self.out)

    def test_auto_writes_every_repository_link_hidden_with_the_check_script(self):
        self.set_banner(repo_check="auto")
        site.build(self.root, self.media, self.out)
        sha = self.cfg["banner"]["first_commit"]["sha"]
        for html in self.pages().values():
            links = re.findall(r"<a [^>]*github\.com[^>]*>", html)
            self.assertEqual(len(links), 3, links)
            self.assertIn(f'href="{self.cfg["repo_url"]}/commit/{sha}"', html)
            for a in links:
                hidden_self = " hidden" in a
                self.assertTrue(hidden_self or re.search(r'<p class="out" data-repo-link hidden><a [^>]*github', html), a)
            self.assertIn('<p class="banner-links" data-repo-link hidden>', html)
            self.assertIn('/repo.js?v=', html)
            self.assertIn('data-repo-api="https://api.github.com/', html)
            self.assertIn('data-repo-name="aimanmalib/sampan-river"', html)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "repo.js")))

    def test_on_shows_the_links_without_the_check(self):
        self.set_banner(repo_check="on")
        site.build(self.root, self.media, self.out)
        for html in self.pages().values():
            self.assertIn('<p class="banner-links"><a href="https://github.com/', html)
            self.assertNotIn("data-repo-link", html)
            self.assertNotIn("repo.js", html)

    def test_off_leaves_the_repository_out(self):
        self.set_banner(repo_check="off")
        site.build(self.root, self.media, self.out)
        for html in self.pages().values():
            self.assertNotIn("github.com", html)
            self.assertNotIn("banner-links", html)
            self.assertIn('class="banner-note"', html)

    def test_unknown_check_stops_the_build(self):
        self.set_banner(repo_check="yes")
        with self.assertRaisesRegex(site.BuildError, "repo_check must be one of"):
            site.build(self.root, self.media, self.out)

    def test_no_deck_link_while_the_deck_is_empty(self):
        site.build(self.root, self.media, self.out)
        for html in self.pages().values():
            self.assertNotIn(".pdf", html)
            self.assertNotIn("application/pdf", html)
        self.assertFalse(os.path.exists(os.path.join(self.out, "deck")))

    def test_deck_link_is_shown_and_copied_per_language(self):
        deck = os.path.join(self.root, "site", "deck")
        os.makedirs(deck, exist_ok=True)
        for code in ("en", "ms"):
            with open(os.path.join(deck, f"fixture-{code}.pdf"), "wb") as f:
                f.write(b"%PDF-1.4 fixture " + code.encode())
        self.set_banner(deck={"en": "site/deck/fixture-en.pdf", "ms": "site/deck/fixture-ms.pdf"})
        site.build(self.root, self.media, self.out)
        for path, code in (("/", "en"), ("/ms/", "ms")):
            href = re.search(r'<a href="(/deck/[^"]+)" type="application/pdf">', self.pages()[path]).group(1)
            self.assertTrue(href.endswith(f"/fixture-{code}.pdf"), href)
            with open(os.path.join(self.out, href.lstrip("/")), "rb") as f:
                self.assertTrue(f.read().startswith(b"%PDF"))
            # A deck makes the link row visible even while the repository links wait for the check.
            self.assertRegex(self.pages()[path], r'<p class="banner-links"><a href="/deck/')

    def test_banner_note_is_a_sourced_claim(self):
        self.assertEqual(set(self.cfg["copy_facts"]["banner.note"]), {"event-start", "first-commit"})


class CspTest(unittest.TestCase):
    def test_csp_allows_only_github_api_beyond_self_for_fetch(self):
        with open(os.path.join(ROOT, "deploy", "nginx.conf"), encoding="utf-8") as f:
            csp = re.search(r'Content-Security-Policy "([^"]+)"', f.read()).group(1)
        directives = dict(d.strip().split(" ", 1) for d in csp.split(";") if d.strip())
        self.assertEqual(directives["connect-src"], "'self' https://api.github.com")
        self.assertEqual(directives["script-src"], "'self'")

    def test_check_script_only_talks_to_the_configured_api(self):
        with open(os.path.join(ROOT, "site", "repo.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertNotRegex(js, r"https?://")
        self.assertIn('getAttribute("data-repo-api")', js)


if __name__ == "__main__":
    unittest.main()
