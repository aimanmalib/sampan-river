"""Music synthesis and mix: determinism, structure and levels. Offline; short configs keep it fast."""
import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest

import numpy as np

from tools import mix, music

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def short_cfg():
    """The committed config shrunk to 8 s at 8 kHz; same keys, so every code path runs."""
    with open(os.path.join(ROOT, "config", "music.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cfg = copy.deepcopy(cfg)
    cfg["sample_rate"], cfg["duration_s"] = 8000, 8.0
    cfg["sections"] = [{"name": "a", "start_s": 0.0, "end_s": 4.0, "density": 0.3, "register": "low"},
                       {"name": "b", "start_s": 4.0, "end_s": 8.0, "density": 0.8, "register": "mid"}]
    cfg["motif"]["at_s"] = 5.0
    cfg["synth"]["reverb"]["length_s"] = 0.5
    return cfg


class MusicTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def wav_sha(self, cfg, name):
        path = music.write_wav(os.path.join(self.tmp, name), music.render(cfg), cfg["sample_rate"])
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_same_config_same_bytes(self):
        cfg = short_cfg()
        self.assertEqual(self.wav_sha(cfg, "a.wav"), self.wav_sha(copy.deepcopy(cfg), "b.wav"))

    def test_seed_changes_the_music(self):
        cfg = short_cfg()
        other = copy.deepcopy(cfg)
        other["seed"] += 1
        self.assertNotEqual(self.wav_sha(cfg, "a.wav"), self.wav_sha(other, "b.wav"))

    def test_length_and_peak_follow_config(self):
        cfg = short_cfg()
        y = music.render(cfg)
        self.assertEqual(len(y), int(cfg["duration_s"] * cfg["sample_rate"]))
        self.assertAlmostEqual(20 * np.log10(np.max(np.abs(y))), cfg["synth"]["peak_db"], places=6)
        self.assertLess(abs(y[0]), 1e-9)
        self.assertLess(abs(y[-1]), 1e-9)

    def test_motif_plays_at_its_time(self):
        cfg = short_cfg()
        sr = cfg["sample_rate"]
        a, _ = music.motif_span(cfg)
        quiet = copy.deepcopy(cfg)
        quiet["synth"]["motif"]["amp"] = 0.0
        loud, soft = music.render(cfg), music.render(quiet)
        # same seed, so the renders differ only by the motif and the peak scaling: before at_s they are proportional
        start = int(a * sr)
        before = slice(0, start - int(0.05 * sr))
        scale = np.dot(loud[before], soft[before]) / np.dot(soft[before], soft[before])
        diff = np.abs(loud - scale * soft)
        self.assertLess(np.max(diff[before]), 1e-9)
        self.assertGreater(np.max(diff[start:start + int(0.5 * sr)]), 0.1)

    def test_sections_must_tile_the_cue(self):
        cfg = short_cfg()
        cfg["sections"][1]["start_s"] = 4.5
        with self.assertRaises(music.MusicError):
            music.render(cfg)
        cfg = short_cfg()
        cfg["sections"][1]["end_s"] = 7.0
        with self.assertRaises(music.MusicError):
            music.render(cfg)

    def test_notes_and_chords(self):
        self.assertAlmostEqual(music.frequency("A4"), 440.0)
        self.assertAlmostEqual(music.frequency("A5"), 880.0)
        self.assertEqual(music.chord_notes("Bm"), ["B", "D", "F#"])
        self.assertEqual(music.chord_notes("A"), ["A", "C#", "E"])
        with self.assertRaises(music.MusicError):
            music.frequency("H4")

    def test_committed_cue_matches_film_length(self):
        with open(os.path.join(ROOT, "config", "music.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        with open(os.path.join(ROOT, "config", "film.json"), encoding="utf-8") as f:
            film = json.load(f)
        self.assertEqual(cfg["duration_s"], film["duration_s"]["target"])
        music.check_sections(cfg)
        self.assertLess(music.motif_span(cfg)[1], cfg["duration_s"])


class MixTest(unittest.TestCase):
    def test_limiter_holds_ceiling_and_leaves_quiet_audio(self):
        sr = 8000
        y = np.full((sr, 2), 0.01)
        y[4000] = 0.9
        out = mix.limit(y, -12, sr, 0.01)
        self.assertLessEqual(np.max(np.abs(out)), 10 ** (-12 / 20) + 1e-12)
        self.assertTrue(np.allclose(out[:3000], y[:3000]))
        self.assertTrue(np.allclose(out[5000:], y[5000:]))

    def test_mix_levels_length_and_ambience_gap(self):
        cfg = short_cfg()
        sr, n = cfg["sample_rate"], int(cfg["duration_s"] * cfg["sample_rate"])
        rng = np.random.default_rng(1)
        theme = music.render(cfg)
        amb = mix.ambience_track([(0.0, 0.01 * rng.standard_normal((4 * sr, 2)))], cfg["duration_s"], sr, 0.1)
        self.assertTrue(np.all(amb[4 * sr:] == 0))
        amb[2 * sr] = 0.9  # a splash far above the ambience average must not clip the mix
        y = mix.mix(theme, amb, sr, cfg)
        self.assertEqual(y.shape, (n, 2))
        self.assertLessEqual(np.max(np.abs(y)), 10 ** (cfg["synth"]["peak_db"] / 20) + 1e-9)
        with self.assertRaises(mix.MixError):
            mix.mix(theme[:-1], amb, sr, cfg)

    def test_segments_follow_shot_windows(self):
        shots = {"shots": [
            {"id": "b", "window_s": [2, 6], "film_s": [4, 8], "accepted": {"landscape": "b.mp4"}},
            {"id": "a", "window_s": [0, 4], "film_s": [0, 4], "accepted": {"landscape": "a.mp4"}}]}
        self.assertEqual([s[0] for s in mix.segments(shots, "landscape")], ["a.mp4", "b.mp4"])
        with self.assertRaises(mix.MixError):
            mix.segments(shots, "portrait")
        shots["shots"][0]["window_s"] = [2, 7]
        with self.assertRaises(mix.MixError):
            mix.segments(shots, "landscape")

    def test_committed_shots_have_landscape_mix_inputs(self):
        with open(os.path.join(ROOT, "config", "shots.json"), encoding="utf-8") as f:
            parts = mix.segments(json.load(f), "landscape")
        self.assertTrue(parts)
        self.assertEqual(parts[0][2][0], 0.0)


if __name__ == "__main__":
    unittest.main()
