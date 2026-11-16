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

## Final films

`python3 tools/edit.py 16x9` then `python3 tools/measure.py 16x9 --write` (2026-11-16). The 1080p picture is the 720p
clips scaled with ffmpeg lanczos; no AI upscaler. Loudness: ffmpeg `ebur128=peak=true` on the final file. Speech: local
check with voice activity detection (decision 0004). caption_cues = cues whose caption band differs from the clean
master at the cue middle (decision 0005); the gaps between cues must not differ. Frames read by a person:
`docs/frames/16x9-cue-01.jpg` to `-10.jpg`.

Read in the frames (2026-11-16): every cue shows its full config text in white with a dark outline, centred above the
bottom edge, one line except cue 8 ("The fare for a real / transfer: 219 satoshis.") and cue 10 ("Bitcoin Cash. Money
that / crosses for almost nothing."); no caption covers the coin. Cue 10 sits under the end card, which shows
"Bitcoin Cash" and "bitcoincash.org" over the dimmed last frame of the jetty shot.

| version | width | height | duration_s | audio | lufs_i | true_peak_db | whisper_words | caption_cues | sha256 |
|---|---|---|---|---|---|---|---|---|---|
| 16x9 | 1920 | 1080 | 60.0 | yes | -13.9 | -1.5 | 0 | 10/10 | 50ca1e0997c12f70913d8c74c49626dff723ab744d3a7419c8a572406c10b0d8 |

<!-- detail:16x9 -->
### 16x9 detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| cue 1 | 1.7 | 7.74 | yes |
| cue 2 | 5.8 | 9.81 | yes |
| cue 3 | 13.25 | 8.29 | yes |
| cue 4 | 18.5 | 7.2 | yes |
| cue 5 | 25.75 | 9.9 | yes |
| cue 6 | 31.75 | 7.9 | yes |
| cue 7 | 37.25 | 8.52 | yes |
| cue 8 | 43.5 | 10.29 | yes |
| cue 9 | 49.5 | 6.58 | yes |
| cue 10 | 57.0 | 15.77 | yes |
| gap 2 | 3.4 | 0.69 | yes |
| gap 3 | 9.5 | 0.58 | yes |
| gap 4 | 15.75 | 0.81 | yes |
| gap 5 | 22.0 | 0.45 | yes |
| gap 6 | 28.75 | 0.6 | yes |
| gap 7 | 34.75 | 0.65 | yes |
| gap 8 | 40.25 | 0.58 | yes |
| gap 9 | 46.25 | 0.65 | yes |
| gap 10 | 53.5 | 0.64 | yes |
| gap 11 | 59.75 | 0.11 | yes |
<!-- /detail:16x9 -->
