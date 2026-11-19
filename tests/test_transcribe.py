import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tools import ledger, transcribe


class CountWords(unittest.TestCase):
    def test_empty_and_punctuation_are_zero(self):
        self.assertEqual(transcribe.count_words(""), 0)
        self.assertEqual(transcribe.count_words(" ... - ! "), 0)

    def test_words_are_counted(self):
        self.assertEqual(transcribe.count_words("Thank you."), 2)
        self.assertEqual(transcribe.count_words("1 coin, 2 banks"), 4)


class SpeechCheckConfig(unittest.TestCase):
    def test_film_requires_zero_words(self):
        cfg = ledger.load_json(ledger.FILM)["audio"]["speech_check"]
        self.assertEqual(cfg["max_words"], 0)
        self.assertTrue({"model", "language", "beam_size", "vad_filter"} <= set(cfg))

    def test_vad_setting_reaches_the_model(self):
        calls = []

        class Model:
            def __init__(self, *a, **k):
                pass

            def transcribe(self, audio, **kw):
                calls.append(kw)
                return [], None

        fake = mock.MagicMock(WhisperModel=Model)
        cfg = {"model": "fake-test", "language": "en", "beam_size": 1}
        with mock.patch.dict("sys.modules", {"faster_whisper": fake}), \
                mock.patch.object(transcribe, "pcm16k", return_value=[]):
            for vad in (True, False):
                transcribe._MODEL.pop("fake-test", None)
                self.assertEqual(transcribe.transcribe("x.wav", dict(cfg, vad_filter=vad)), "")
        self.assertEqual([c["vad_filter"] for c in calls], [True, False])


class ExitCode(unittest.TestCase):
    def run_main(self, text):
        out = io.StringIO()
        with mock.patch.object(transcribe, "transcribe", return_value=text), redirect_stdout(out):
            rc = transcribe.main(["transcribe.py", "clip.mp4"])
        return rc, json.loads(out.getvalue())

    def test_silent_audio_passes(self):
        rc, row = self.run_main("")
        self.assertEqual((rc, row["words"], row["file"]), (0, 0, "clip.mp4"))

    def test_any_word_fails(self):
        rc, row = self.run_main("Thank you.")
        self.assertEqual((rc, row["words"]), (1, 2))


class SpeechMatch(unittest.TestCase):
    def test_numbers_match_whichever_way_they_are_written(self):
        self.assertEqual(transcribe.number_words(219), "two hundred and nineteen")
        self.assertEqual(transcribe.number_words(1005), "one thousand five")
        self.assertEqual(transcribe.script_words("$5, 219 satoshis"), transcribe.script_words("five dollars two hundred and nineteen satoshis"))

    def test_words_heard_in_order_over_script_words(self):
        script = "Sending five dollars should not cost five dollars."
        self.assertEqual(transcribe.speech_match("Sending $5 should not cost $5!", script), 1.0)
        self.assertEqual(transcribe.speech_match("", script), 0.0)
        self.assertEqual(transcribe.speech_match("sending dollars should cost", script), 0.5)
        self.assertEqual(transcribe.speech_match("cost not should sending", script), 0.125)
        self.assertEqual(transcribe.speech_match("anything", ""), 0.0)
        self.assertEqual(transcribe.lcs_len(list("abcbdab"), list("bdcaba")), 4)


if __name__ == "__main__":
    unittest.main()
