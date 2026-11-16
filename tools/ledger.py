"""Credit ledger for video generations: one JSON line per idempotency key in log/generations.jsonl.

Flow for every generation (decision 0001):
1. `GET /v1/me` gives the live balance.
2. `record_before_submit(row, balance)` runs the credit guard and appends the row (status `submitted`) BEFORE the request
   is sent. The guard refuses when balance - cost < reserve_ai_film, or when credits already spent + cost > media_cap.
3. `update(key, fields)` merges the outcome (job id, status, me_after, sha256, file) into that same row.
Both steps hold an exclusive flock on `<log>.lock`, so two processes cannot overwrite each other's rows.
`record_me(balance)` appends a balance-only row (status `me_only`) without spending anything.

CLI: python3 tools/ledger.py spent
"""
import contextlib
import fcntl
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "log", "generations.jsonl")
FILM = os.path.join(ROOT, "config", "film.json")
FIELDS = ("utc", "shot", "model", "route", "idempotency_key", "credits", "me_before", "me_after", "job_id", "status",
          "refunded", "sha256", "file")
STATUSES = ("submitted", "done", "failed", "me_only")


class GuardRefused(RuntimeError):
    """The credit guard refused a submission. Stop; do not retry with a different key."""


class InvalidRow(ValueError):
    pass


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def limits(config):
    c = config["credits"]
    return float(c["reserve_ai_film"]), float(c["media_cap"])


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextlib.contextmanager
def locked(path=LOG):
    """Exclusive cross-process lock on a separate file (os.replace swaps the log inode)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read(path=LOG):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def next_key(prefix, rows):
    """Sequential idempotency key `<prefix>-NNNN`, unique within the ledger.

    A sequence is enough: one generation runs at a time and the ledger refuses duplicate keys. Random hex suffixes
    were dropped because secret scanners read them as API keys (the value is not a secret, but it must not look like one).
    """
    used = {r.get("idempotency_key") for r in rows}
    n = len(rows) + 1
    while f"{prefix}-{n:04d}" in used:
        n += 1
    return f"{prefix}-{n:04d}"


def spent(rows):
    """Media credits charged so far: every row except balance checks and refunded failures."""
    return sum(float(r.get("credits") or 0) for r in rows if r.get("status") != "me_only" and not r.get("refunded"))


def check_guard(balance, cost, rows, config):
    """Raise GuardRefused unless balance - cost >= reserve AND spent + cost <= cap. Return remaining Media budget."""
    reserve, cap = limits(config)
    balance, cost = float(balance), float(cost)
    if balance - cost < reserve:
        raise GuardRefused(f"balance {balance:g} - cost {cost:g} = {balance - cost:g} is below the reserve {reserve:g}")
    already = spent(rows)
    if already + cost > cap + 1e-9:
        raise GuardRefused(f"spent {already:g} + cost {cost:g} = {already + cost:g} is above the Media cap {cap:g}")
    return cap - already - cost


def _append(row, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return row


def record_before_submit(row, balance, path=LOG, config=None):
    """Guard + append a `submitted` row. Return the row written. A key already in the log is an error."""
    key = row.get("idempotency_key")
    if not key:
        raise InvalidRow("idempotency_key is required before submitting")
    if row.get("credits") is None:
        raise InvalidRow("credits (expected cost) is required before submitting")
    config = config if config is not None else load_json(FILM)
    with locked(path):
        rows = read(path)
        if any(r.get("idempotency_key") == key for r in rows):
            raise InvalidRow(f"key {key} is already in the log; retry with that row, do not record a new one")
        check_guard(balance, row["credits"], rows, config)
        full = {f: None for f in FIELDS}
        full.update(utc=utc_now(), me_before=float(balance), status="submitted", refunded=False)
        full.update({k: v for k, v in row.items() if k not in ("status", "me_before", "refunded")})
        full["credits"] = float(full["credits"])
        return _append(full, path)


def record_me(balance, path=LOG, note=None):
    """Append a balance-only row (no spending)."""
    row = {f: None for f in FIELDS}
    row.update(utc=utc_now(), credits=0.0, me_before=float(balance), status="me_only", refunded=False)
    if note:
        row["note"] = note
    with locked(path):
        return _append(row, path)


def update(key, fields, path=LOG):
    """Merge `fields` into the row with idempotency key `key`; atomic rewrite under the lock. Return the new row."""
    if "status" in fields and fields["status"] not in STATUSES:
        raise InvalidRow(f"status {fields['status']!r} is not one of {STATUSES}")
    with locked(path):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        hit = None
        for i, line in enumerate(lines):
            if line.strip() and json.loads(line).get("idempotency_key") == key:
                hit = i
        if hit is None:
            raise KeyError(f"key {key} is not in the log")
        new = dict(json.loads(lines[hit]), **fields)
        lines[hit] = json.dumps(new, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".generations-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return new


def main(argv):
    if len(argv) < 2 or argv[1] != "spent":
        print("usage: python3 tools/ledger.py spent", file=sys.stderr)
        return 2
    reserve, cap = limits(load_json(FILM))
    s = spent(read())
    print(f"Media credits spent {s:g} of cap {cap:g} (remaining {cap - s:g}); reserve kept for other work {reserve:g}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
