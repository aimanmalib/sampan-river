# Measured

Numbers below are printed by the tools named in each section, not estimated. Media files stay out of git and are
identified by sha256.

## Audio stems

`python3 tools/mix.py --orientation landscape` (2026-11-16). Run twice; both runs gave the same bytes.
Loudness: ffmpeg `ebur128=peak=true`. Speech: `python3 tools/transcribe.py` (faster-whisper `small.en`, voice activity
detection on, decision 0004).

| file | seconds | channels | peak_dbfs | rms_dbfs | lufs_i | whisper_words | sha256 |
|---|---|---|---|---|---|---|---|
| music.wav | 60.0 | 1 | -1.0 | -16.76 | -16.9 | 0 | 6193f97f6ee52cc288f046a70e422c4db14c16de114aff18d9709e96dbd18dd6 |
| mix-landscape.wav | 60.0 | 2 | -2.22 | -17.4 | -14.6 | 0 | 3439c43e05d117698bc36bf12161dcb2b14b91719966f7c811696feee5f7b3f9 |

Ambience sources (clip audio inside the edit windows, before levelling), from `tools/mix.py` `decode`:

| clip | window | rms_dbfs | peak_dbfs |
|---|---|---|---|
| toll-bridge-L1.mp4 | 5 to 27 s | -37.0 | -2.3 (one splash at window 20.9 s) |
| crossing-L1.mp4 | 4 to 22 s | -37.5 | -12.9 |
| green-bank-L1.mp4 | 8 to 22 s | -40.9 | -7.4 |

Spectrum of the mix: `docs/frames/mix-landscape-spectrum.jpg`. Read: broadband river sound under tonal music lines from
0 to about 54 s; from 54 s (end card) only the music's tonal lines remain, fading to silence by 60 s; higher kalimba
lines become denser from about 40 s (the `arrival` section, high register).

The final film loudness (-14 LUFS integrated, true peak at most -1 dBTP) is set and measured in the edit step.
