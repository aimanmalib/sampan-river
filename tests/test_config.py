"""Shape checks on the committed config and docs (limits, captions, facts, shots). No owner data is locked here."""
import json
import os
import re
import unittest

from tools import prompts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f) if rel.endswith(".json") else f.read()


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.film = load("config/film.json")
        self.cues = load("config/captions.en.json")["cues"]

    def test_credit_limits_not_loosened(self):
        c = self.film["credits"]
        self.assertGreaterEqual(c["reserve_ai_film"], 450)
        self.assertLessEqual(c["media_cap"], 120)
        b = c["budget_generations"]
        self.assertLessEqual(sum(b.values()) * c["cost_per_generation"], c["media_cap"])

    def test_film_length_and_cues_fit(self):
        d = self.film["duration_s"]
        self.assertTrue(d["min"] <= d["target"] <= d["max"])
        self.assertTrue(45 <= d["min"] and d["max"] <= 75)
        self.assertLessEqual(max(c["end"] for c in self.cues), d["target"])
        for a, b in zip(self.cues, self.cues[1:]):
            self.assertLessEqual(a["end"], b["start"], a["text"])
        for c in self.cues:
            self.assertLess(c["start"], c["end"])

    def test_hook_caption_in_first_seconds_and_short(self):
        d = self.film["duration_s"]
        first = min(self.cues, key=lambda c: c["start"])
        self.assertLess(first["start"], d["hook_max_s"])
        self.assertLessEqual(len(first["text"].split()), d["hook_max_words"])

    def test_every_fact_is_sourced(self):
        facts = load("docs/FACTS.md")
        for c in self.cues:
            if c["fact"]:
                self.assertRegex(facts, r"\| `" + re.escape(c["fact"]) + r"` \|.*https://", c["text"])

    def test_no_forbidden_words_in_captions(self):
        bad = re.compile(r"guarantee|risk.?free|always \$?1|trustless|revolutionary|financial advice|\u2014|!", re.I)
        for c in self.cues:
            self.assertIsNone(bad.search(c["text"]), c["text"])

    def test_shots_cover_story_and_prompt_excludes_text_and_speech(self):
        data = prompts.load_shots()
        self.assertTrue(3 <= len(data["shots"]) <= 7)
        for s in data["shots"]:
            p = prompts.build(data, s["id"])
            for word in ("No text", "no logos", "no speech", "no music"):
                self.assertIn(word.lower(), p.lower())
            self.assertEqual(set(s["orientation"]), {"landscape", "portrait"})
            self.assertLess(s["window_s"][0], s["window_s"][1])
        ends = sorted(s["film_s"] for s in data["shots"])
        self.assertEqual(ends[0][0], 0.0)
        self.assertEqual(ends[-1][1], self.film["end_card"]["start_s"])

    def test_prize_address_consistent(self):
        self.assertIn(self.film["prize_address"], load("README.md"))
        self.assertTrue(self.film["prize_address"].startswith("bitcoincash:"))


if __name__ == "__main__":
    unittest.main()
