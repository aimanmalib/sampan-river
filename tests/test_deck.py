"""The slide deck (decision 0016), offline: the committed PDFs match their stamp, and stale or swapped files are caught."""
import json
import os
import shutil
import tempfile
import unittest

from tools import deck, site

ROOT = site.ROOT


class CommittedDeckTest(unittest.TestCase):
    def test_committed_pdfs_are_current(self):
        self.assertEqual(deck.problems(ROOT), [])

    def test_banner_links_the_printed_pdfs(self):
        cfg, _ = deck.load(ROOT)
        for lang in cfg["languages"]:
            self.assertEqual(cfg["banner"]["deck"][lang["code"]], deck.out_path(cfg, lang["code"]))

    def test_each_language_has_its_own_text(self):
        cfg, langs = deck.load(ROOT)
        en, ms = (deck.visible_text(deck.render(ROOT, cfg, langs, c)) for c in ("en", "ms"))
        self.assertIn("The real numbers", en)
        self.assertIn("Angka sebenar", ms)
        self.assertNotIn("The real numbers", ms)

    def test_fee_slide_links_the_transaction_and_every_claim_has_a_fact(self):
        cfg, langs = deck.load(ROOT)
        fare = deck.slides(deck.render(ROOT, cfg, langs, "en"))[2]
        self.assertIn(f'href="{cfg["links"]["fee_tx"]}"', fare)
        for key in ("deck.fare.tx", "deck.fare.price", "deck.fare.cents", "deck.fare.figure"):
            self.assertIn(key, cfg["copy_facts"])
        with open(os.path.join(ROOT, "docs", "FACTS.md"), encoding="utf-8") as f:
            self.assertEqual(site.check_copy(langs, cfg, f.read()), [])


class DeckCopyTest(unittest.TestCase):
    """A copy of the inputs and the committed PDFs, changed one way per test."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="deck-test-")
        for part in ("config", "site"):
            shutil.copytree(os.path.join(ROOT, part), os.path.join(self.root, part))
        cfg, _ = deck.load(ROOT)
        os.makedirs(os.path.join(self.root, "docs", "frames"))
        for rel in cfg["deck"]["frames"].values():
            shutil.copy(os.path.join(ROOT, rel), os.path.join(self.root, rel))
        self.assertEqual(deck.problems(self.root), [])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def edit_json(self, rel, change):
        path = os.path.join(self.root, rel)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        change(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def found(self):
        return "\n".join(deck.problems(self.root))

    def test_new_text_makes_the_printed_pdf_stale(self):
        self.edit_json("site/lang/ms.json", lambda d: d["deck"]["story"].update(title="Cerita baharu"))
        self.assertIn("ms: site/deck/the-river-fare-ms.pdf was printed from other text", self.found())
        self.assertNotIn("en:", self.found())

    def test_new_address_makes_the_printed_pdf_stale(self):
        self.edit_json("config/site.json", lambda d: d.update(prize_address="bitcoincash:zfixture"))
        self.assertIn("en: site/deck/the-river-fare-en.pdf was printed from other text", self.found())

    def test_pdf_swapped_by_hand_is_caught(self):
        with open(os.path.join(self.root, "site", "deck", "the-river-fare-en.pdf"), "ab") as f:
            f.write(b"\n% edited\n")
        self.assertIn("en: site/deck/the-river-fare-en.pdf is not the file the stamp records", self.found())

    def test_a_file_that_is_not_a_pdf_is_caught(self):
        with open(os.path.join(self.root, "site", "deck", "the-river-fare-ms.pdf"), "wb") as f:
            f.write(b"<html>not a pdf</html>")
        self.assertIn("ms: site/deck/the-river-fare-ms.pdf is not a PDF", self.found())

    def test_oversized_pdf_is_caught(self):
        self.edit_json("config/site.json", lambda d: d["deck"].update(max_bytes=1000))
        self.assertIn("bytes, over 1000", self.found())

    def test_address_missing_from_its_slide_is_caught(self):
        path = os.path.join(self.root, "site", "deck", "deck.html")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace('<p class="address">{{v:address}}</p>', ""))
        self.assertIn("slide 5 does not show the prize address", self.found())

    def test_banned_word_in_the_deck_is_caught(self):
        self.edit_json("site/lang/en.json", lambda d: d["deck"]["fare"].update(cents="A guaranteed fare."))
        self.assertIn("en: deck uses 'guaranteed'", self.found())


if __name__ == "__main__":
    unittest.main()
