"""VE Studio client with the credit guard (decision 0001). Every value comes from config/film.json `ve` and `credits`.

- Before EVERY submit: `GET /v1/me`, then ledger.record_before_submit() runs the guard and writes the row. Only then is
  `POST /v1/t2v` sent (multipart, `X-API-Key` + `X-Idempotency-Key`). A timeout or `409 in_progress` is retried with the
  SAME key only.
- Poll `GET /v1/jobs/{id}` every `poll_s` up to `wait_max_s`. Past that limit the row stays `submitted`; continue later
  with `resume --key <key>` (no new credits).
- Download WITH the API key (without it the server returns a small JSON body named .mp4). Check size, ffprobe
  (resolution, duration), sha256, mode 0444. Existing files are never overwritten.
- After every generation: `GET /v1/me` again -> `me_after`. A failed job counts as refunded only when me_after shows it.
- The key is read from the environment or a key file and is never printed or logged.

Usage: python3 tools/ve.py me
       python3 tools/ve.py generate --shot <id> --orientation landscape|portrait --out media/clips/<file>.mp4
       python3 tools/ve.py resume --key <idempotency_key> --out media/clips/<file>.mp4
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import ledger, prompts  # noqa: E402


class VEError(RuntimeError):
    pass


def read_key(cfg, environ=os.environ):
    """API key from env var `key_env`, else from the env-style file named by `key_file_env` (or `.env` in the repo)."""
    name = cfg["key_env"]
    if environ.get(name):
        return environ[name]
    path = environ.get(cfg["key_file_env"]) or os.path.join(ROOT, ".env")
    if os.path.exists(os.path.expanduser(path)):
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.strip() == name and v.strip():
                    return v.strip().strip("\"'")
    raise VEError(f"{name} is not set (environment or key file)")


def http_urllib(method, url, headers, body=None, timeout=60):
    """(status, response headers, bytes). HTTP errors are returned as a status, not raised."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def multipart(fields):
    boundary = "sr" + uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode() for n, v in fields]
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check_clip(probe, resolution, cfg):
    """Problems found by ffprobe against config (resolution, duration within tolerance). Empty = pass."""
    w, h = (int(x) for x in resolution.split("x"))
    video = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    if not video:
        return ["no video stream"]
    problems = []
    if (video[0].get("width"), video[0].get("height")) != (w, h):
        problems.append(f"resolution {video[0].get('width')}x{video[0].get('height')} is not {resolution}")
    duration = float(probe.get("format", {}).get("duration") or 0)
    if abs(duration - cfg["clip_s"]) > cfg["duration_tolerance_s"]:
        problems.append(f"duration {duration:.3f}s is not {cfg['clip_s']}+-{cfg['duration_tolerance_s']}")
    return problems


class Client:
    def __init__(self, config, key=None, http=http_urllib, sleep=time.sleep, log=ledger.LOG, probe=ffprobe):
        self.config, self.cfg = config, config["ve"]
        self._key = key if key is not None else read_key(self.cfg)
        self.http, self.sleep, self.log, self.probe = http, sleep, log, probe

    def _headers(self, **extra):
        return dict({"X-API-Key": self._key, "Accept": "application/json"}, **extra)

    def _json(self, method, path, body=None, headers=None, timeout=60):
        st, hd, raw = self.http(method, self.cfg["api_base"] + path, headers or self._headers(), body, timeout)
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {"_not_json": raw[:200].decode("utf-8", "replace")}
        return st, hd, data

    def me(self):
        st, _, d = self._json("GET", "/v1/me")
        if st != 200 or "credits" not in d:
            raise VEError(f"GET /v1/me returned HTTP {st}")
        return float(d["credits"])

    def submit(self, shot, orientation, prompt, key=None):
        """GET /v1/me -> guard + ledger row -> POST. Return (key, submit response)."""
        model = self.cfg["models"][orientation]
        cost = float(self.config["credits"]["cost_per_generation"])
        key = key or f"{shot}-{orientation[0]}-{uuid.uuid4().hex[:16]}"
        balance = self.me()
        ledger.record_before_submit({"shot": shot, "model": model, "route": self.cfg["route"], "idempotency_key": key,
                                     "credits": cost, "prompt": prompt}, balance, self.log, self.config)
        body, ctype = multipart([("model", model), ("prompt", prompt)])
        headers = self._headers(**{"X-Idempotency-Key": key, "Content-Type": ctype})
        return key, self._post(key, body, headers)

    def _post(self, key, body, headers):
        for _ in range(self.cfg["submit_attempts"]):
            try:
                st, hd, d = self._json("POST", self.cfg["route"], body, headers, timeout=self.cfg["submit_timeout_s"])
            except OSError:  # timeout or dropped socket: retry with the SAME key
                self.sleep(self.cfg["poll_s"])
                continue
            if st == 409 and hd.get("Idempotent-Status") == "in_progress":
                self.sleep(int(hd.get("Retry-After") or 5))
                continue
            if st == 200 and d.get("id"):
                ledger.update(key, {"job_id": d["id"], "credits": float(d.get("credits_charged", 0))}, self.log)
                return d
            ledger.update(key, {"credits": 0.0, "status": "failed", "refunded": True,
                                "error": f"HTTP {st} {str(d.get('error') or d.get('detail') or '')[:200]}"}, self.log)
            raise VEError(f"submit refused with HTTP {st}")
        raise VEError(f"submit failed after {self.cfg['submit_attempts']} attempts; key {key} stays in the log")

    def wait(self, job_id):
        start = time.monotonic()
        while True:
            st, _, d = self._json("GET", f"/v1/jobs/{job_id}")
            if st == 200 and d.get("status") in ("completed", "failed"):
                return d
            if time.monotonic() - start > self.cfg["wait_max_s"]:
                raise VEError(f"job {job_id} not finished within wait_max_s; resume later with the same key")
            self.sleep(self.cfg["poll_s"])

    def download(self, job, out, resolution):
        if os.path.exists(out):
            raise VEError(f"{out} already exists; raw clips are never overwritten")
        url = job.get("download_url") or job.get("output_url")
        st, _, raw = self.http("GET", url, self._headers(Accept="*/*"), None, self.cfg["download_timeout_s"])
        if st != 200 or len(raw) <= self.cfg["min_download_bytes"]:
            raise VEError(f"download HTTP {st}, {len(raw)} bytes (not a video)")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        part = out + ".part"
        with open(part, "xb") as f:
            f.write(raw)
        try:
            problems = check_clip(self.probe(part), resolution, self.cfg)
            if problems:
                raise VEError("ffprobe: " + "; ".join(problems))
            os.link(part, out)
        finally:
            os.unlink(part)
        os.chmod(out, 0o444)
        return {"sha256": sha256_file(out), "file": os.path.basename(out)}

    def finish(self, key, job_id, out, orientation):
        """Wait for an already submitted job, download, record me_after. No new submit."""
        job = self.wait(job_id)
        if job["status"] == "failed":
            row = next(r for r in ledger.read(self.log) if r.get("idempotency_key") == key)
            after = self.me()
            refunded = after >= float(row["me_before"])
            fields = {"status": "failed", "me_after": after, "refunded": refunded, "error": str(job.get("error"))[:200]}
            if refunded:
                fields["credits"] = 0.0
            ledger.update(key, fields, self.log)
            raise VEError(f"job {job_id} failed (refunded: {refunded})")
        fields = self.download(job, out, self.cfg["resolution"][orientation])
        fields.update(status="done", me_after=self.me())
        return ledger.update(key, fields, self.log)

    def generate(self, shot, orientation, prompt, out):
        key, d = self.submit(shot, orientation, prompt)
        return self.finish(key, d["id"], out, orientation)

    def resume(self, key, out):
        rows = [r for r in ledger.read(self.log) if r.get("idempotency_key") == key]
        if not rows or not rows[-1].get("job_id"):
            raise VEError(f"no job_id for {key}; resubmit with the same key instead")
        if rows[-1].get("status") != "submitted":
            raise VEError(f"{key} has status {rows[-1].get('status')!r}, not 'submitted'")
        orientation = next(o for o, m in self.cfg["models"].items() if m == rows[-1]["model"])
        return self.finish(key, rows[-1]["job_id"], out, orientation)


def main(argv):
    ap = argparse.ArgumentParser(description="VE Studio client with credit guard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("me", help="record the live balance (no spending)")
    g = sub.add_parser("generate")
    g.add_argument("--shot", required=True)
    g.add_argument("--orientation", choices=("landscape", "portrait"), required=True)
    g.add_argument("--out", required=True)
    r = sub.add_parser("resume")
    r.add_argument("--key", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args(argv[1:])
    client = Client(ledger.load_json(ledger.FILM))
    if a.cmd == "me":
        balance = client.me()
        ledger.record_me(balance)
        print(f"VE Studio balance: {balance:g} credits (recorded)")
        return 0
    if a.cmd == "resume":
        row = client.resume(a.key, a.out)
    else:
        prompt = prompts.build(prompts.load_shots(), a.shot)
        row = client.generate(a.shot, a.orientation, prompt, a.out)
    print(f"{row['shot']}: {row['file']} sha256 {row['sha256'][:12]} me_after {row['me_after']:g}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
