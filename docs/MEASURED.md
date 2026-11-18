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

`python3 tools/edit.py 16x9` then `python3 tools/measure.py 16x9 --write` (2026-11-18, after the cue 5 and end card
wording change; same clips, windows and mix as 2026-11-16). The 1080p picture is the 720p
clips scaled with ffmpeg lanczos; no AI upscaler. Loudness: ffmpeg `ebur128=peak=true` on the final file. Speech: local
check with voice activity detection (decision 0004). caption_cues = cues whose caption band differs from the clean
master at the cue middle (decision 0005); the gaps between cues must not differ. Frames read by a person:
`docs/frames/16x9-cue-01.jpg` to `-10.jpg`.

Read in the frames (2026-11-18): every cue shows its full config text in white with a dark outline, centred above the
bottom edge, one line except cue 8 ("The fare for a real / transfer: 219 satoshis.") and cue 10 ("Bitcoin Cash. Money
that / crosses for almost nothing."); no caption covers the coin. Cue 5 reads "A digital dollar on Bitcoin Cash." on one
line under the boat, with the coin clear above it. Cue 10 sits under the end card, which shows "Bitcoin Cash" and "Get a
wallet: bitcoincash.org" in full over the dimmed last frame of the jetty shot; neither card line touches the caption.

`python3 tools/edit.py 9x16` then `python3 tools/measure.py 9x16 --write` (2026-11-16, before the cue 5 and end card
wording change of 2026-11-18; this row is replaced when 9:16 is cut again). Cut from the same landscape
clips, windows and mix as 16:9 (decision 0006): the full picture at 1080 x 608 (lanczos from 1280 x 720) centred over a
blurred, dimmed copy of the same frame. The 9:16 caption band (rows 68% to 80%) was measured here for the first time:
weakest cue 9.78, largest gap 0.24, against limits 4.0 and 1.5. Frames read by a person: `docs/frames/9x16-cue-01.jpg`
to `-10.jpg`. Read in the frames (2026-11-16): every cue shows its full config text in two lines of white with a dark
outline, centred in the blurred area below the picture, except cue 9 ("Less than a tenth of a cent.") on one line; no
caption overlaps the picture, the boat or the coin. Cue 10 sits under the end card ("Bitcoin Cash", "bitcoincash.org")
drawn over the dimmed jetty picture in the middle of the frame.

| version | width | height | duration_s | audio | lufs_i | true_peak_db | whisper_words | caption_cues | sha256 |
|---|---|---|---|---|---|---|---|---|---|
| 16x9 | 1920 | 1080 | 60.0 | yes | -13.9 | -1.5 | 0 | 10/10 | aeda33e02351f7d789df4431b3ded04eb64301f94ce4525003ea2001e14b2a73 |
| 9x16 | 1080 | 1920 | 60.0 | yes | -13.9 | -1.5 | 0 | 10/10 | 821983538a99f5e48c44534903093f7c0f2f08a80268bc0901eca06fb1abb32a |

<!-- detail:16x9 -->
### 16x9 detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| cue 1 | 1.7 | 7.74 | yes |
| cue 2 | 5.8 | 9.81 | yes |
| cue 3 | 13.25 | 8.29 | yes |
| cue 4 | 18.5 | 7.2 | yes |
| cue 5 | 25.75 | 8.4 | yes |
| cue 6 | 31.75 | 7.9 | yes |
| cue 7 | 37.25 | 8.52 | yes |
| cue 8 | 43.5 | 10.29 | yes |
| cue 9 | 49.5 | 6.58 | yes |
| cue 10 | 57.0 | 15.76 | yes |
| gap 2 | 3.4 | 0.69 | yes |
| gap 3 | 9.5 | 0.58 | yes |
| gap 4 | 15.75 | 0.81 | yes |
| gap 5 | 22.0 | 0.45 | yes |
| gap 6 | 28.75 | 0.6 | yes |
| gap 7 | 34.75 | 0.65 | yes |
| gap 8 | 40.25 | 0.58 | yes |
| gap 9 | 46.25 | 0.65 | yes |
| gap 10 | 53.5 | 0.64 | yes |
| gap 11 | 59.75 | 0.12 | yes |
<!-- /detail:16x9 -->

<!-- detail:9x16 -->
### 9x16 detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| cue 1 | 1.7 | 10.61 | yes |
| cue 2 | 5.8 | 13.46 | yes |
| cue 3 | 13.25 | 11.12 | yes |
| cue 4 | 18.5 | 10.09 | yes |
| cue 5 | 25.75 | 13.56 | yes |
| cue 6 | 31.75 | 13.6 | yes |
| cue 7 | 37.25 | 12.86 | yes |
| cue 8 | 43.5 | 15.42 | yes |
| cue 9 | 49.5 | 9.78 | yes |
| cue 10 | 57.0 | 21.53 | yes |
| gap 2 | 3.4 | 0.2 | yes |
| gap 3 | 9.5 | 0.12 | yes |
| gap 4 | 15.75 | 0.21 | yes |
| gap 5 | 22.0 | 0.05 | yes |
| gap 6 | 28.75 | 0.0 | yes |
| gap 7 | 34.75 | 0.12 | yes |
| gap 8 | 40.25 | 0.24 | yes |
| gap 9 | 46.25 | 0.24 | yes |
| gap 10 | 53.5 | 0.22 | yes |
| gap 11 | 59.75 | 0.03 | yes |
<!-- /detail:9x16 -->

## Thumbnail

`python3 tools/thumb.py` (2026-11-16): `crossing-L1.mp4` at 10.0 s (inside its edit window, so the still is a frame of the
film), 1280 x 720 lanczos, JPEG 95,358 bytes, sha256 f97ba088f9bea2cbc2875917a50a8e4731868ffd445d8ffa96f8881c17e4768a.
Copy: `docs/frames/thumbnail.jpg`. Read in the image (2026-11-16): the paper rower in a conical hat at the stern of a
folded paper boat, the gold coin with a raised "1" in the bow; "The River Fare" in large cream letters with a dark
outline at the top right, "A dollar crosses to Bitcoin Cash" below it; neither line touches the rower, the oar or the coin.

<!-- sharpness -->
## Sharpness (9:16 layouts)

Variance of the Laplacian of the luma, same scene region shown at each layout's size (tools/sharpness.py).

| clip | t (s) | blur_fill | 4:5 | 1:1 |
|---|---|---|---|---|
| toll-bridge-L1.mp4 | 10.5 | 69.3 | 6.6 | 12.8 |
| toll-bridge-L1.mp4 | 16.0 | 63.8 | 7.0 | 13.4 |
| toll-bridge-L1.mp4 | 21.5 | 40.1 | 4.7 | 8.5 |
| crossing-L1.mp4 | 8.5 | 92.7 | 9.1 | 18.6 |
| crossing-L1.mp4 | 13.0 | 89.3 | 8.7 | 17.5 |
| crossing-L1.mp4 | 17.5 | 67.5 | 6.4 | 12.4 |
| green-bank-L1.mp4 | 11.5 | 40.2 | 4.5 | 8.1 |
| green-bank-L1.mp4 | 15.0 | 40.3 | 4.4 | 7.8 |
| green-bank-L1.mp4 | 18.5 | 54.8 | 5.3 | 10.1 |

Mean ratio to blur_fill: 4:5 0.103, 1:1 0.196. Limit: 0.55. Chosen: blur_fill (no crop passes).
<!-- /sharpness -->
