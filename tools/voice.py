"""Narration takes from the ElevenLabs text-to-speech API, guarded and ledgered (decision 0012).

Script: each caption cue is read as shown on screen. `spoken(text)` turns the screen text into the words to say with
config/voice.json `spoken_map` ("$5" -> "five dollars"); a cue may carry `say`, which must normalise to the same words.
Guard before every request: `GET /v1/user/subscription` gives the characters left; a request is sent only when
left - chars >= reserve_chars AND the ledger total + chars <= char_budget. The ledger row (log/voice.jsonl: id, take,
chars, text_sha8, sub_left_before, status "sent") is written BEFORE the request and updated after (status "done",
sha256 of the mp3, duration_s, whisper_match). No text, voice id or key goes into the ledger.
Cache: `<cache_dir>/<id>-<hash>-t<take>.mp3` + `.json` (alignment). A cue whose hash already has a passing take is never
sent again; a take that fails the whisper match leaves room for another, up to max_takes.
HTTP is injectable (tests); the default client connects over IPv4 only (the key is bound to the host's IPv4 address).
Usage: python3 tools/voice.py balance | generate [<cue id> ...]
"""
import base64
import contextlib
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import ledger, transcribe  # noqa: E402

CONFIG = os.path.join(ROOT, "config", "voice.json")
CAPTION_FILES = (os.path.join(ROOT, "config", "captions.en.json"), os.path.join(ROOT, "config", "captions.short.en.json"))
COUNTED = ("sent", "done")


class VoiceError(RuntimeError):
    """Stop: the guard refused, the API refused, or a take is missing."""


# ---------- script ----------
def spoken(text, spoken_map):
    """Screen text -> words to say. Longer keys first, so "$5" wins over "5"; a key matches whole tokens only."""
    out = text
    for key in sorted(spoken_map, key=len, reverse=True):
        out = re.sub(r"(?<![\w$])" + re.escape(key) + r"(?!\w)", spoken_map[key], out)
    return out


normalise = transcribe.script_words


def say(cue, cfg):
    """The text sent for a cue: `say` when present (it must match the screen text), else spoken(text)."""
    screen = spoken(cue["text"], cfg["spoken_map"])
    if cue.get("say") is not None and normalise(cue["say"]) != normalise(screen):
        raise VoiceError(f"{cue.get('id')}: say {cue['say']!r} does not match the screen text {screen!r}")
    return cue.get("say") or screen


def text_hash(text, cfg, voice_id):
    """Cache key: text + voice + model settings (the voice id only enters as part of a hash)."""
    blob = json.dumps({"text": text, "voice": voice_id, "model": cfg["model_id"], "lang": cfg["language_code"],
                       "format": cfg["output_format"]}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------- ledger ----------
def read_ledger(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def chars_spent(rows):
    return sum(int(r["chars"]) for r in rows if r.get("status") in COUNTED)


def guard(left, chars, rows, cfg):
    """Raise VoiceError unless the account keeps reserve_chars and the ledger stays within char_budget."""
    if left - chars < cfg["reserve_chars"]:
        raise VoiceError(f"guard: {left} left - {chars} = {left - chars} < reserve {cfg['reserve_chars']}")
    total = chars_spent(rows) + chars
    if total > cfg["char_budget"]:
        raise VoiceError(f"guard: ledger {total} > char_budget {cfg['char_budget']}")


def _write_rows(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".voice-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def record_sent(path, row, left, cfg):
    """Guard, then append the `sent` row; both under the ledger lock. Returns the row."""
    with ledger.locked(path):
        rows = read_ledger(path)
        guard(left, row["chars"], rows, cfg)
        full = dict(row, utc=ledger.utc_now(), sub_left_before=int(left), status="sent")
        _write_rows(path, rows + [full])
        return full


def update_row(path, cue_id, take, fields):
    with ledger.locked(path):
        rows = read_ledger(path)
        hits = [i for i, r in enumerate(rows) if r["id"] == cue_id and r["take"] == take]
        if not hits:
            raise KeyError(f"{cue_id} take {take} is not in the ledger")
        rows[hits[-1]] = dict(rows[hits[-1]], **fields)
        _write_rows(path, rows)
        return rows[hits[-1]]


# ---------- HTTP ----------
@contextlib.contextmanager
def ipv4_only():
    real = socket.getaddrinfo

    def v4(host, port, family=0, *args, **kwargs):
        return real(host, port, socket.AF_INET, *args, **kwargs)
    socket.getaddrinfo = v4
    try:
        yield
    finally:
        socket.getaddrinfo = real


def http(method, url, headers, body, timeout):
    """(status, bytes) over IPv4. HTTP errors return their status; network errors raise."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with ipv4_only():
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()


def subscription_left(cfg, key, send=http):
    status, body = send("GET", cfg["api_base"] + "/v1/user/subscription", {"xi-api-key": key}, None, cfg["timeout_s"])
    if status != 200:
        raise VoiceError(f"subscription: HTTP {status}")
    s = json.loads(body)
    return int(s["character_limit"]) - int(s["character_count"])


def post_tts(cfg, key, voice_id, text, send=http):
    url = (f"{cfg['api_base']}/v1/text-to-speech/{voice_id}/with-timestamps?output_format={cfg['output_format']}")
    body = json.dumps({"text": text, "model_id": cfg["model_id"], "language_code": cfg["language_code"]}).encode()
    return send("POST", url, {"xi-api-key": key, "Content-Type": "application/json"}, body, cfg["timeout_s"])


# ---------- takes ----------
def take_path(cache_dir, cue_id, h, take, ext="mp3"):
    return os.path.join(cache_dir, f"{cue_id}-{h}-t{take}.{ext}")


def passing_take(rows, cue_id, h, cfg):
    """The best `done` take of this cue and hash that passed the whisper match, or None."""
    ok = [r for r in rows if r["id"] == cue_id and r.get("hash") == h and r.get("status") == "done"
          and float(r.get("whisper_match") or 0) >= cfg["match_min"]]
    return max(ok, key=lambda r: (float(r["whisper_match"]), -r["take"])) if ok else None


def synth(cue, cfg, *, key, voice_id, ledger_path, cache_dir, hear, send=http):
    """Return the ledger row of a passing take for `cue`, sending at most what the guard and max_takes allow.
    `hear(mp3_path, text) -> match` scores a take (whisper)."""
    text = say(cue, cfg)
    h = text_hash(text, cfg, voice_id)
    while True:
        rows = read_ledger(ledger_path)
        hit = passing_take(rows, cue["id"], h, cfg)
        if hit:
            return hit
        mine = [r for r in rows if r["id"] == cue["id"] and r.get("hash") == h]
        if any(r["status"] == "sent" for r in mine):
            raise VoiceError(f"{cue['id']}: a take was sent but never finished; check the ledger before sending again")
        take = max((r["take"] for r in mine), default=0) + 1
        if take > cfg["max_takes"]:
            raise VoiceError(f"{cue['id']}: {cfg['max_takes']} takes and none passed the whisper match")
        left = subscription_left(cfg, key, send)
        record_sent(ledger_path, {"id": cue["id"], "take": take, "chars": len(text), "hash": h,
                                  "text_sha8": hashlib.sha256(text.encode()).hexdigest()[:8]}, left, cfg)
        try:
            status, body = post_tts(cfg, key, voice_id, text, send)
        except OSError as e:  # network: the characters may have been charged, so the row stays `sent`
            raise VoiceError(f"{cue['id']} take {take}: {type(e).__name__}") from e
        if status != 200:
            update_row(ledger_path, cue["id"], take, {"status": "failed", "http": status})
            raise VoiceError(f"{cue['id']} take {take}: HTTP {status}")
        reply = json.loads(body)
        mp3 = base64.b64decode(reply["audio_base64"])
        align = reply.get("normalized_alignment") or reply["alignment"]
        os.makedirs(cache_dir, exist_ok=True)
        path = take_path(cache_dir, cue["id"], h, take)
        with open(path, "wb") as f:
            f.write(mp3)
        with open(take_path(cache_dir, cue["id"], h, take, "json"), "w", encoding="utf-8") as f:
            json.dump({"text": text, "alignment": align}, f)
        match = round(float(hear(path, text)), 3)
        update_row(ledger_path, cue["id"], take, {"status": "done", "sha256": hashlib.sha256(mp3).hexdigest(),
                                                  "duration_s": round(span(align)[1], 3), "whisper_match": match})


def span(alignment):
    """(first, last) seconds of non-space characters in an ElevenLabs alignment."""
    chars = alignment["characters"]
    idx = [i for i, c in enumerate(chars) if c.strip()]
    if not idx:
        raise VoiceError("alignment has no spoken characters")
    return (float(alignment["character_start_times_seconds"][idx[0]]),
            float(alignment["character_end_times_seconds"][idx[-1]]))


def all_cues():
    out = []
    for path in CAPTION_FILES:
        out += ledger.load_json(path)["cues"]
    return out


def main(argv):
    cfg = ledger.load_json(CONFIG)
    if not argv or argv[0] not in ("balance", "generate"):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    key, voice_id = os.environ.get(cfg["key_env"]), os.environ.get(cfg["voice_env"])
    if not key or (argv[0] == "generate" and not voice_id):
        print(f"set {cfg['key_env']} and {cfg['voice_env']} in the environment", file=sys.stderr)
        return 2
    if argv[0] == "balance":
        print(json.dumps({"characters_left": subscription_left(cfg, key), "ledger_chars":
                          chars_spent(read_ledger(os.path.join(ROOT, cfg["ledger"])))}))
        return 0
    check = ledger.load_json(ledger.FILM)["audio"]["speech_check"]

    def hear(path, text):
        return transcribe.speech_match(transcribe.transcribe(path, check), text)
    wanted = set(argv[1:])
    for cue in all_cues():
        if wanted and cue["id"] not in wanted:
            continue
        row = synth(cue, cfg, key=key, voice_id=voice_id, ledger_path=os.path.join(ROOT, cfg["ledger"]),
                    cache_dir=os.path.join(ROOT, cfg["cache_dir"]), hear=hear)
        print(json.dumps({k: row.get(k) for k in ("id", "take", "chars", "duration_s", "whisper_match")}))
        time.sleep(0.2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
