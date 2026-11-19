"""Share button and the fee linked to its transaction (decision 0013), offline on fixture media."""
import json
import os
import re
import unittest
from urllib.parse import quote

from tests import test_site
from tools import page_links, site

ROOT = test_site.ROOT


def facts_txid():
    with open(os.path.join(ROOT, "docs", "FACTS.md"), encoding="utf-8") as f:
        ids = page_links.fact_hashes(f.read(), "fee-tx")
    assert len(ids) == 1, ids
    return ids.pop()


class ShareBuildTest(unittest.TestCase):
    tearDown = test_site.SiteBuildTest.tearDown
    write_measured = test_site.SiteBuildTest.write_measured
    write_cfg = test_site.SiteBuildTest.write_cfg
    page = test_site.SiteBuildTest.page

    def setUp(self):
        test_site.SiteBuildTest.setUp(self)
        self.write_cfg()

    def lang(self, code, edit):
        path = os.path.join(self.root, "site", "lang", code + ".json")
        with open(path, encoding="utf-8") as f:
            copy = json.load(f)
        edit(copy)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(copy, f)

    def pages(self):
        return {l["path"]: self.page(l["path"].strip("/") + "/index.html" if l["path"] != "/" else "index.html")
                for l in self.cfg["languages"]}

    def test_both_pages_share_their_own_canonical_url(self):
        site.build(self.root, self.media, self.out)
        base = "https://" + self.cfg["domain"]
        for path, page in self.pages().items():
            url = base + path
            box = re.search(r'<div class="share" data-share data-url="([^"]+)"', page)
            self.assertIsNotNone(box, path)
            self.assertEqual(box.group(1), url)
            self.assertIn('class="share-btn"', page)
            self.assertIn('<script src="/share.js?v=', page)
            targets = re.findall(r'class="share-to" href="([^"]+)"', page)
            self.assertEqual(len(targets), len(self.cfg["share"]["targets"]))
            for href in targets:
                self.assertIn(quote(url, safe=""), href)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "share.js")))

    def test_fee_links_to_the_transaction_in_facts(self):
        site.build(self.root, self.media, self.out)
        txid = facts_txid()
        for path, page in self.pages().items():
            links = re.findall(r'<a class="src" href="([^"]+)" rel="noopener">([^<]+)<span class="sr">', page)
            self.assertEqual(len(links), 1, path)
            self.assertIn(txid, links[0][0])
            self.assertTrue(links[0][1].startswith("219 satoshi"), links[0][1])
            self.assertNotIn("[[", page)

    def test_wrong_txid_stops_the_build(self):
        links = dict(self.cfg["links"], fee_tx="https://bchexplorer.info/tx/" + "0" * 64)
        self.write_cfg(links=links)
        with self.assertRaisesRegex(site.BuildError, "fee-tx"):
            site.build(self.root, self.media, self.out)

    def test_copy_is_escaped_before_the_link_is_added(self):
        self.lang("en", lambda c: c["facts"].update(fee="Fee <b>of</b> [[fee]]219 satoshis[[/fee]] & more"))
        site.build(self.root, self.media, self.out)
        page = self.page("index.html")
        self.assertIn("Fee &lt;b&gt;of&lt;/b&gt; <a class=\"src\" href=", page)
        self.assertIn("&amp; more", page)
        self.assertNotIn("<b>of</b>", page)

    def test_mark_outside_its_keys_stops_the_build(self):
        self.lang("ms", lambda c: c["hero"].update(lede=c["hero"]["lede"] + " [[fee]]x[[/fee]]"))
        with self.assertRaisesRegex(site.BuildError, "may not carry link mark fee"):
            site.build(self.root, self.media, self.out)

    def test_unbalanced_mark_stops_the_build(self):
        self.lang("en", lambda c: c["facts"].update(fee=c["facts"]["fee"].replace("[[/fee]]", "")))
        with self.assertRaisesRegex(site.BuildError, "not one open and one close"):
            site.build(self.root, self.media, self.out)

    def test_share_can_be_switched_off_from_config(self):
        self.write_cfg(share=dict(self.cfg["share"], enabled=False))
        site.build(self.root, self.media, self.out)
        for page in self.pages().values():
            self.assertNotIn("data-share", page)
            self.assertNotIn("share.js", page)


class ShareCopyTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.langs = {}
        for l in self.cfg["languages"]:
            with open(os.path.join(ROOT, "site", "lang", l["code"] + ".json"), encoding="utf-8") as f:
                self.langs[l["code"]] = site.flatten(json.load(f))

    def test_every_language_labels_the_button_and_each_target(self):
        for code, flat in self.langs.items():
            for key in ("share.button", "share.label", "share.text", "share.copy_link", "share.copied",
                        "share.copy_failed", "facts.fee_link_label"):
                self.assertTrue(flat.get(key, "").strip(), f"{code} {key}")
            for t in self.cfg["share"]["targets"]:
                self.assertTrue(flat.get(f"share.targets.{t['id']}"), f"{code} {t['id']}")
        self.assertNotEqual(self.langs["en"]["share.button"], self.langs["ms"]["share.button"])
        self.assertNotEqual(self.langs["en"]["share.text"], self.langs["ms"]["share.text"])

    def test_share_targets_are_https_and_take_url_and_text(self):
        for t in self.cfg["share"]["targets"]:
            self.assertTrue(t["url"].startswith("https://"), t["id"])
            self.assertIn("{url}", t["url"])
            self.assertIn("{text}", t["url"])

    def test_share_text_is_a_sourced_claim(self):
        self.assertIn("share.text", self.cfg["copy_facts"])

    def test_share_script_has_no_third_party_source(self):
        with open(os.path.join(ROOT, "site", "share.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertLessEqual(len(js.splitlines()), 120)
        self.assertNotRegex(js, r"https?://")
        self.assertIn("AbortError", js)


if __name__ == "__main__":
    unittest.main()
