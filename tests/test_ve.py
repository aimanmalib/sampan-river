"""VE client: guard before POST, ledger row before POST, same key on retry, key never logged. Fake HTTP, no network."""
import json
import os
import tempfile
import unittest

from tools import ledger, ve

SECRET = "fixture-" + "value-never-logged"
CFG = {
    "credits": {"reserve_ai_film": 450, "media_cap": 120, "cost_per_generation": 9},
    "ve": {"api_base": "https://ve.example", "route": "/v1/t2v",
           "models": {"landscape": "land-model", "portrait": "port-model"},
           "resolution": {"landscape": "1280x720", "portrait": "720x1280"}, "clip_s": 30, "duration_tolerance_s": 0.2,
           "key_env": "TEST_VE_KEY", "key_file_env": "TEST_VE_KEY_FILE", "poll_s": 0, "wait_max_s": 5,
           "idempotency_prefix": "t-gen", "submit_attempts": 3, "submit_timeout_s": 1, "min_download_bytes": 10, "download_timeout_s": 1},
}


class FakeHTTP:
    def __init__(self, balances, posts, log):
        self.balances, self.posts, self.log, self.calls = list(balances), list(posts), log, []

    def __call__(self, method, url, headers, body=None, timeout=60):
        self.calls.append((method, url, dict(headers)))
        if url.endswith("/v1/me"):
            return 200, {}, json.dumps({"credits": self.balances.pop(0)}).encode()
        if method == "POST":
            self.calls[-1] += (ledger.read(self.log),)  # ledger state at the moment of the POST
            nxt = self.posts.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        if "/v1/jobs/" in url:
            return 200, {}, json.dumps({"status": "completed", "download_url": "https://ve.example/dl"}).encode()
        return 200, {}, b"x" * 100


def ok_post(job="job-1"):
    return 200, {}, json.dumps({"id": job, "credits_charged": 9}).encode()


def probe(_path):
    return {"streams": [{"codec_type": "video", "width": 1280, "height": 720}], "format": {"duration": "30.0"}}


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "generations.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, http):
        return ve.Client(CFG, key=SECRET, http=http, sleep=lambda s: None, log=self.log, probe=probe)

    def test_guard_refusal_sends_no_post(self):
        http = FakeHTTP([455], [], self.log)
        with self.assertRaises(ledger.GuardRefused):
            self.client(http).submit("toll-bridge", "landscape", "p")
        self.assertEqual([c[0] for c in http.calls], ["GET"])
        self.assertEqual(ledger.read(self.log), [])

    def test_cap_refusal_sends_no_post(self):
        for i in range(13):
            ledger.record_before_submit({"shot": "s", "model": "m", "route": "r", "idempotency_key": f"old{i}",
                                         "credits": 9}, 1000, self.log, CFG)
        http = FakeHTTP([1000], [], self.log)
        with self.assertRaises(ledger.GuardRefused):
            self.client(http).submit("crossing", "landscape", "p")
        self.assertNotIn("POST", [c[0] for c in http.calls])

    def test_row_written_before_post(self):
        http = FakeHTTP([700], [ok_post()], self.log)
        key, _ = self.client(http).submit("toll-bridge", "landscape", "p")
        post = [c for c in http.calls if c[0] == "POST"][0]
        self.assertEqual([r["idempotency_key"] for r in post[3]], [key])
        self.assertEqual(post[3][0]["me_before"], 700.0)
        self.assertEqual(post[2]["X-Idempotency-Key"], key)

    def test_new_key_is_sequential_not_random(self):
        ledger.record_me(700, self.log)
        http = FakeHTTP([700], [ok_post()], self.log)
        key, _ = self.client(http).submit("toll-bridge", "landscape", "p")
        self.assertEqual(key, "t-gen-0002")

    def test_retry_uses_same_key(self):
        busy = (409, {"Idempotent-Status": "in_progress", "Retry-After": "0"}, b"{}")
        http = FakeHTTP([700], [TimeoutError(), busy, ok_post()], self.log)
        self.client(http).submit("toll-bridge", "landscape", "p")
        keys = {c[2]["X-Idempotency-Key"] for c in http.calls if c[0] == "POST"}
        self.assertEqual(len(keys), 1)
        self.assertEqual(len(ledger.read(self.log)), 1)

    def test_generate_records_done_and_me_after_without_key(self):
        http = FakeHTTP([700, 691], [ok_post()], self.log)
        out = os.path.join(self.tmp.name, "clips", "a.mp4")
        r = self.client(http).generate("toll-bridge", "landscape", "p", out)
        self.assertEqual((r["status"], r["me_before"], r["me_after"], r["file"]), ("done", 700.0, 691.0, "a.mp4"))
        self.assertRegex(r["sha256"], r"^[0-9a-f]{64}$")
        with open(self.log, encoding="utf-8") as f:
            self.assertNotIn(SECRET, f.read())

    def test_failed_job_refunded_only_when_balance_shows_it(self):
        for after, refunded in ((700, True), (691, False)):
            log = os.path.join(self.tmp.name, f"g{after}.jsonl")
            http = FakeHTTP([700, after], [ok_post()], log)
            c = ve.Client(CFG, key=SECRET, http=http, sleep=lambda s: None, log=log, probe=probe)
            c.wait = lambda job_id: {"status": "failed", "error": "x"}
            with self.assertRaises(ve.VEError):
                c.generate("crossing", "landscape", "p", os.path.join(self.tmp.name, f"{after}.mp4"))
            r = ledger.read(log)[0]
            self.assertEqual((r["status"], r["refunded"], r["credits"]), ("failed", refunded, 0.0 if refunded else 9.0))

    def test_key_read_from_env_or_file_never_from_repo_config(self):
        self.assertEqual(ve.read_key(CFG["ve"], {"TEST_VE_KEY": "abc"}), "abc")
        path = os.path.join(self.tmp.name, "k.env")
        with open(path, "w", encoding="utf-8") as f:
            f.write("OTHER=1\nTEST_VE_KEY='from-file'\n")
        self.assertEqual(ve.read_key(CFG["ve"], {"TEST_VE_KEY_FILE": path}), "from-file")
        self.assertNotIn("key", json.dumps(CFG["ve"]).replace("key_env", "").replace("key_file_env", ""))


if __name__ == "__main__":
    unittest.main()
