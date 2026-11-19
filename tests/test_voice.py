"""Narration client (decision 0012): script words, guard, ledger before the request, cache. Fake HTTP, no key, no API."""
import base64
import copy
import json
import os
import shutil
import tempfile
import unittest

from tools import transcribe, voice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cfg(**over):
    with open(os.path.join(ROOT, "config", "voice.json"), encoding="utf-8") as f:
        c = json.load(f)
    c.update(over)
    return c


def alignment(text, start=0.2, per_char=0.05):
    chars = list(text)
    starts = [round(start + i * per_char, 3) for i in range(len(chars))]
    return {"characters": chars, "character_start_times_seconds": starts,
            "character_end_times_seconds": [round(s + per_char, 3) for s in starts]}


class FakeApi:
    """Records every call; `left` characters remain; `log_path` lets the test see the ledger at POST time."""

    def __init__(self, left, log_path=None, tts_status=200):
        self.left, self.log_path, self.tts_status, self.calls, self.ledger_at_post = left, log_path, tts_status, [], []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url))
        if url.endswith("/v1/user/subscription"):
            return 200, json.dumps({"character_limit": 100000, "character_count": 100000 - self.left}).encode()
        if self.log_path:
            self.ledger_at_post.append(voice.read_ledger(self.log_path))
        text = json.loads(body)["text"]
        reply = {"audio_base64": base64.b64encode(b"ID3fake-" + text.encode()).decode(),
                 "alignment": alignment(text), "normalized_alignment": alignment(text)}
        return self.tts_status, json.dumps(reply).encode()

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


class VoiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "voice.jsonl")
        self.cache = os.path.join(self.tmp, "voice")
        self.cue = {"id": "film-01", "start": 0.2, "end": 3.2, "text": "Sending $5 should not cost $5.", "fact": None}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_synth(self, api, c=None, hear=lambda p, t: 1.0, cue=None):
        return voice.synth(cue or self.cue, c or cfg(), key="k", voice_id="v", ledger_path=self.log,
                           cache_dir=self.cache, hear=hear, send=api)

    def test_spoken_reads_the_screen_text_aloud(self):
        c = cfg()
        self.assertEqual(voice.spoken("Sending $5 should not cost $5.", c["spoken_map"]),
                         "Sending five dollars should not cost five dollars.")
        self.assertEqual(voice.spoken("The fare for a real transfer: 219 satoshis.", c["spoken_map"]),
                         "The fare for a real transfer: two hundred and nineteen satoshis.")
        self.assertEqual(voice.spoken("$50 and 2190", {"$5": "five dollars", "219": "x"}), "$50 and 2190")

    def test_every_caption_cue_has_an_id_and_says_its_screen_text(self):
        c, ids = cfg(), []
        for cue in voice.all_cues():
            ids.append(cue["id"])
            said = voice.say(cue, c)
            self.assertEqual(transcribe.script_words(said), transcribe.script_words(cue["text"]), cue["id"])
            self.assertEqual(transcribe.script_words(said), transcribe.script_words(voice.spoken(cue["text"], c["spoken_map"])))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(i.startswith(("film-", "short-")) for i in ids))

    def test_say_that_differs_from_the_screen_is_refused(self):
        with self.assertRaises(voice.VoiceError):
            voice.say(dict(self.cue, say="Sending ten dollars should not cost five dollars."), cfg())
        self.assertEqual(voice.say(dict(self.cue, say="Sending 5 dollars should not cost five dollars"), cfg()),
                         "Sending 5 dollars should not cost five dollars")

    def test_ledger_row_is_written_before_the_request(self):
        api = FakeApi(left=10000, log_path=self.log)
        row = self.run_synth(api)
        self.assertEqual(len(api.posts()), 1)
        before = api.ledger_at_post[0]
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]["status"], "sent")
        self.assertEqual(before[0]["sub_left_before"], 10000)
        self.assertEqual(before[0]["chars"], len(voice.say(self.cue, cfg())))
        self.assertEqual(row["status"], "done")
        self.assertEqual(len(row["sha256"]), 64)
        self.assertEqual(row["whisper_match"], 1.0)
        text = json.dumps(voice.read_ledger(self.log))
        self.assertNotIn("Sending", text)
        self.assertNotIn('"v"', text)
        self.assertTrue(os.path.exists(voice.take_path(self.cache, "film-01", row["hash"], 1)))

    def test_guard_refuses_low_balance_without_posting(self):
        c = cfg()
        api = FakeApi(left=c["reserve_chars"] + 5)
        with self.assertRaises(voice.VoiceError):
            self.run_synth(api, c)
        self.assertEqual(api.posts(), [])
        self.assertEqual(voice.read_ledger(self.log), [])

    def test_guard_refuses_over_budget_without_posting(self):
        c = cfg(char_budget=40)
        api = FakeApi(left=100000)
        self.run_synth(api, c, cue=dict(self.cue, id="a", text="Short line."))
        with self.assertRaises(voice.VoiceError):
            self.run_synth(api, c)
        self.assertEqual(len(api.posts()), 1)
        self.assertLessEqual(voice.chars_spent(voice.read_ledger(self.log)), 40)

    def test_same_hash_is_not_sent_again(self):
        api = FakeApi(left=100000)
        first = self.run_synth(api)
        again = self.run_synth(api)
        self.assertEqual(len(api.posts()), 1)
        self.assertEqual(first["take"], again["take"])
        changed = copy.deepcopy(self.cue)
        changed["text"] = "Sending $5 should cost almost nothing."
        self.run_synth(api, cue=changed)
        self.assertEqual(len(api.posts()), 2)

    def test_failed_match_takes_another_up_to_max_takes(self):
        api, scores = FakeApi(left=100000), iter([0.5, 0.95])
        row = self.run_synth(api, hear=lambda p, t: next(scores))
        self.assertEqual((row["take"], len(api.posts())), (2, 2))
        api2 = FakeApi(left=100000)
        with self.assertRaises(voice.VoiceError):
            self.run_synth(api2, cfg(max_takes=2), hear=lambda p, t: 0.1, cue=dict(self.cue, id="film-02"))
        self.assertEqual(len(api2.posts()), 2)

    def test_http_error_marks_the_row_failed_and_stops(self):
        api = FakeApi(left=100000, tts_status=401)
        with self.assertRaises(voice.VoiceError):
            self.run_synth(api)
        rows = voice.read_ledger(self.log)
        self.assertEqual([r["status"] for r in rows], ["failed"])
        self.assertEqual(voice.chars_spent(rows), 0)

    def test_unfinished_take_blocks_a_new_request(self):
        voice.record_sent(self.log, {"id": "film-01", "take": 1, "chars": 30,
                                     "hash": voice.text_hash(voice.say(self.cue, cfg()), cfg(), "v")}, 100000, cfg())
        api = FakeApi(left=100000)
        with self.assertRaises(voice.VoiceError):
            self.run_synth(api)
        self.assertEqual(api.posts(), [])

    def test_span_skips_spaces(self):
        a = alignment("  Hi there ", start=0.0, per_char=0.1)
        self.assertEqual(voice.span(a), (0.2, 1.0))

    def test_config_keeps_no_voice_id_or_key(self):
        with open(os.path.join(ROOT, "config", "voice.json"), encoding="utf-8") as f:
            raw = f.read()
        c = json.loads(raw)
        self.assertNotIn("sk_", raw)
        self.assertNotIn("voice_id", c)
        self.assertLessEqual(c["char_budget"], 4000)
        self.assertGreaterEqual(c["duck_db"], 10)


if __name__ == "__main__":
    unittest.main()
