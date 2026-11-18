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

    def test_end_card_claims_are_sourced(self):
        facts = load("docs/FACTS.md")
        e = self.film["end_card"]
        for line, fact in e.get("line_facts", {}).items():
            self.assertIn(line, e["lines"])
            self.assertRegex(facts, r"\| `" + re.escape(fact) + r"` \|.*https://", line)
        for line in e["lines"]:
            if re.search(r"wallet|dollar|fee|cent", line, re.I):
                self.assertIn(line, e.get("line_facts", {}), f"end card claim without a fact: {line}")

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

    def test_locked_style_points_to_a_decision_and_a_logged_clip(self):
        lock = load("config/shots.json")["style_locked"]
        self.assertTrue(os.path.exists(os.path.join(ROOT, lock["decision"])))
        done = [json.loads(line) for line in load("log/generations.jsonl").splitlines() if line.strip()]
        self.assertIn(lock["test_clip"], [r["file"] for r in done if r["status"] == "done" and r["sha256"]])

    def test_accepted_clips_are_logged_and_windows_fit(self):
        data = load("config/shots.json")
        rows = [json.loads(line) for line in load("log/generations.jsonl").splitlines() if line.strip()]
        done = {r["file"]: r for r in rows if r["status"] == "done" and r["sha256"]}
        shots_md = load("docs/SHOTS.md")
        clip_s = self.film["ve"]["clip_s"]
        for s in data["shots"]:
            a, b = s["window_s"]
            f0, f1 = s["film_s"]
            self.assertAlmostEqual(b - a, f1 - f0, places=3, msg=s["id"])
            self.assertTrue(0 <= a < b <= clip_s, s["id"])
            for orientation, name in s.get("accepted", {}).items():
                self.assertIn(name, done, f"{s['id']} {orientation}: no done ledger row")
                self.assertEqual(done[name]["shot"], s["id"])
                line = next((ln for ln in shots_md.splitlines() if name in ln and "accepted" in ln), None)
                self.assertIsNotNone(line, f"{name} not marked accepted in docs/SHOTS.md")
                self.assertIn(f"accepted, window {a:g} to {b:g} s", line, f"{name}: window in SHOTS.md differs from config")

    def test_prize_address_consistent(self):
        self.assertIn(self.film["prize_address"], load("README.md"))
        self.assertTrue(self.film["prize_address"].startswith("bitcoincash:"))


if __name__ == "__main__":
    unittest.main()
