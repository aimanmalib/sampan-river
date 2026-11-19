"""Public text checks: the fare wording and every fee number in the README must match the fact list."""
import glob
import json
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


# README table label for each MEASURED version row.
README_LABELS = {"16x9": "16:9", "9x16": "9:16", "short-9x16": "9:16 short"}


def measured_rows():
    """version -> (seconds, lufs, true peak, cues, sha256) from the final-file table in docs/MEASURED.md."""
    out, head = {}, None
    for line in read("docs/MEASURED.md").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[:1] == ["version"] and "caption_cues" in cells:
            head = cells
        elif head and len(cells) == len(head) and cells[0] in README_LABELS:
            r = dict(zip(head, cells))
            out[cells[0]] = (r["duration_s"], r["lufs_i"], r["true_peak_db"], r["caption_cues"], r["sha256"])
    return out


def readme_rows():
    """README label -> cells of the files table."""
    out = {}
    for line in read("README.md").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 8 and cells[0] in README_LABELS.values():
            out[cells[0]] = cells
    return out


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

    def test_readme_files_table_matches_measured(self):
        measured, rows = measured_rows(), readme_rows()
        self.assertEqual(set(measured), set(README_LABELS), "MEASURED is missing a final file")
        for version, (seconds, lufs, peak, cues, sha) in measured.items():
            row = rows.get(README_LABELS[version])
            self.assertIsNotNone(row, f"README has no row for {version}")
            self.assertEqual(row[2], seconds, version)
            self.assertEqual(row[3], f"{lufs} LUFS", version)
            self.assertEqual(row[4], f"{peak} dBTP", version)
            done, total = cues.split("/")
            self.assertEqual(row[6], f"{done} of {total} cues", version)
            self.assertEqual(row[7], f"`{sha[:8]}...`", version)

    def test_readme_names_the_film_page(self):
        with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
            domain = json.load(f)["domain"]
        self.assertIn(f"https://{domain}", read("README.md"))

    def test_helpers_detect_bad_text(self):
        self.assertEqual(fee_numbers("paid 2,190 satoshis and 5 satoshi"), [2190, 5])
        self.assertIn("grain of rice", "Pays a fare of one GRAIN OF RICE".lower())


if __name__ == "__main__":
    unittest.main()
