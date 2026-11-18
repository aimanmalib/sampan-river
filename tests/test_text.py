"""Public text checks: the fare wording and every fee number in the README must match the fact list."""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The fare is shown by a caption, not by an object in the picture (decision 0001, amended).
RETIRED_PHRASES = ("grain of rice",)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def public_texts():
    """README plus the site copy files once they exist."""
    paths = ["README.md"] + sorted(
        os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "site", "lang", "*.json")))
    return {p: read(p) for p in paths}


def facts():
    """Map fact id to its claim column in docs/FACTS.md."""
    out = {}
    for line in read("docs/FACTS.md").splitlines():
        m = re.match(r"\|\s*`([a-z0-9-]+)`\s*\|\s*([^|]+)\|", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def fee_numbers(text):
    """Satoshi amounts stated in a text."""
    return [int(n.replace(",", "")) for n in re.findall(r"([\d,]+)\s+satoshis?\b", text)]


class TextTest(unittest.TestCase):
    def test_no_retired_phrases(self):
        for path, text in public_texts().items():
            for phrase in RETIRED_PHRASES:
                self.assertNotIn(phrase, text.lower(), f"{path} still says '{phrase}'")

    def test_fee_numbers_match_facts(self):
        f = facts()
        sourced = set(fee_numbers(f["fee-tx"]))
        self.assertTrue(sourced, "fee-tx claim has no satoshi amount")
        readme = read("README.md")
        stated = fee_numbers(readme)
        self.assertTrue(stated, "README states no fee")
        for n in stated:
            self.assertIn(n, sourced, f"README fee {n} satoshis is not in fact fee-tx")

    def test_fare_wording_matches_fee_fact(self):
        claim = facts()["fee-usd"].lower()
        readme = " ".join(read("README.md").split()).lower()
        self.assertIn("less than a tenth of a us cent", claim)
        self.assertIn("pays a fare of less than a tenth of a us cent", readme)

    def test_helpers_detect_bad_text(self):
        self.assertEqual(fee_numbers("paid 2,190 satoshis and 5 satoshi"), [2190, 5])
        self.assertIn("grain of rice", "Pays a fare of one GRAIN OF RICE".lower())


if __name__ == "__main__":
    unittest.main()
