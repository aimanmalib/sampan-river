"""Local speech check with faster-whisper (decision 0001: the film audio must contain zero words).

Settings come from config/film.json `audio.speech_check`. CPU, int8; the model loads once per process.
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
                                          vad_filter=False)
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
