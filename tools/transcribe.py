"""Local speech check with faster-whisper (decision 0001: the film audio must contain zero words).

Settings come from config/film.json `audio.speech_check`. CPU, int8; the model loads once per process.
`vad_filter` (decision 0004): Silero voice activity detection runs first, because without it the model invents stock
outro phrases on music and river sound.
A narrated version (decision 0012) is checked the other way: `speech_match` = words of the script heard in order.
Usage: python3 tools/transcribe.py <media file> [<media file> ...]
Prints one JSON object per file: {"file", "words", "text"}. Exit 1 when any file has more than `max_words` words.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools import ledger  # noqa: E402

_MODEL = {}


def count_words(text):
    """Words that contain at least one letter or digit (whisper punctuation alone is not speech)."""
    return len([w for w in text.split() if re.search(r"[A-Za-z0-9]", w)])


def lcs_len(a, b):
    """Length of the longest common subsequence of two word lists."""
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n):
    """English words for 0 <= n < 1,000,000 (British "and" after hundred), so "219" and "two hundred and nineteen"
    count as the same words whichever way the speech model writes them."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " and " + number_words(n % 100))
    return number_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + number_words(n % 1000))


def script_words(text):
    """Normalised words: lower case, "$5" read as "5 dollars", digits as words, punctuation dropped."""
    t = re.sub(r"\$(\d+)", r"\1 dollars", text.lower().replace("'", "").replace(",", ""))
    t = re.sub(r"\d+", lambda m: " " + number_words(int(m.group())) + " " if int(m.group()) < 10 ** 6 else m.group(), t)
    return re.findall(r"[a-z0-9]+", t)


def speech_match(transcript, script):
    """Decision 0012: words of the script heard in order (LCS) / words of the script. 0..1."""
    want = script_words(script)
    return round(lcs_len(script_words(transcript), want) / len(want), 3) if want else 0.0


def pcm16k(path):
    """Decode to float32 mono 16 kHz with ffmpeg."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def transcribe(path, cfg):
    from faster_whisper import WhisperModel  # late import: unit tests do not need the package
    name = cfg["model"]
    if name not in _MODEL:
        _MODEL[name] = WhisperModel(name, device="cpu", compute_type="int8")
    segments, _ = _MODEL[name].transcribe(pcm16k(path), language=cfg["language"], beam_size=cfg["beam_size"],
                                          vad_filter=cfg["vad_filter"])
    return " ".join(s.text.strip() for s in segments).strip()


def check(path, cfg):
    text = transcribe(path, cfg)
    return {"file": os.path.basename(path), "words": count_words(text), "text": text}


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-2], file=sys.stderr)
        return 2
    cfg = ledger.load_json(ledger.FILM)["audio"]["speech_check"]
    worst = 0
    for path in argv[1:]:
        result = check(path, cfg)
        worst = max(worst, result["words"])
        print(json.dumps(result, ensure_ascii=False))
    return 1 if worst > cfg["max_words"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
