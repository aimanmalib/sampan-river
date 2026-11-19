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

| version | width | height | duration_s | audio | lufs_i | true_peak_db | whisper_words | speech_match | caption_cues | sha256 |
|---|---|---|---|---|---|---|---|---|---|---|
| 16x9 | 1920 | 1080 | 60.0 | yes | -14.0 | -1.4 | 67 | 0.973 | 10/10 | cfff07f113d73e36b0dcf99c87288f5886f0de7b79de53ce26b2fdba0eadba85 |
| 9x16 | 1080 | 1920 | 60.0 | yes | -14.0 | -1.4 | 67 | 0.973 | 14/14 | 1530a180ad7361cad01bdca7400b35fcf899e00d235625229e17e17f344fd3cc |
| short-9x16 | 1080 | 1920 | 18.6 | yes | -14.0 | -3.2 | 0 | - | 4/4 | 253a5ebdf345118d5c62e0d38f5811b0a0848961496f1db2ababa374e827b8f1 |
| 16x9-tanpa-suara | 1920 | 1080 | 60.0 | yes | -13.9 | -1.5 | 0 | - | 10/10 | 53598d66b72a52e9fe4e4c554fa38df4faad54bfe54b777b7975b9b345b4a0e8 |
| 9x16-tanpa-suara | 1080 | 1920 | 60.0 | yes | -13.9 | -1.5 | 0 | - | 14/14 | f990017876f5177cce948ad74d5269eda8e5a39e7fce9d47e817c4ee7252e2cf |

<!-- detail:16x9 -->
### 16x9 detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none. Heard: "Sending $5 should not cost $5. The old bridge takes a cut from everyone. One rower takes the river instead. She carries $1 across. A digital dollar on Bitcoin Cash. It is designed to hold $1. The coin does not shrink on the way. The fare for a real transfer, 219 satoshis. Less than a tenth of a cent. Bitcoin Cash. Money that crosses for almost nothing."; speech match 0.973.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| cue 1 | 1.81 | 7.78 | yes |
| cue 2 | 5.09 | 9.89 | yes |
| cue 3 | 12.25 | 8.23 | yes |
| cue 4 | 17.21 | 7.27 | yes |
| cue 5 | 24.33 | 9.2 | yes |
| cue 6 | 30.25 | 7.94 | yes |
| cue 7 | 36.13 | 8.53 | yes |
| cue 8 | 43.09 | 10.28 | yes |
| cue 9 | 47.75 | 6.87 | yes |
| cue 10 | 56.75 | 15.77 | yes |
| gap 3 | 8.79 | 0.64 | yes |
| gap 4 | 14.75 | 0.89 | yes |
| gap 5 | 20.71 | 0.79 | yes |
| gap 6 | 27.33 | 0.48 | yes |
| gap 7 | 33.25 | 0.66 | yes |
| gap 8 | 39.13 | 0.68 | yes |
| gap 9 | 45.84 | 0.64 | yes |
| gap 10 | 51.75 | 0.6 | yes |
| gap 11 | 59.5 | 0.13 | yes |
<!-- /detail:16x9 -->

<!-- detail:9x16 -->
### 9x16 detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none. Heard: "Sending $5 should not cost $5. The old bridge takes a cut from everyone. One rower takes the river instead. She carries $1 across. A digital dollar on Bitcoin Cash. It is designed to hold $1. The coin does not shrink on the way. The fare for a real transfer, 219 satoshis. Less than a tenth of a cent. Bitcoin Cash. Money that crosses for almost nothing."; speech match 0.973.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| top cue 1 | 1.81 | 7.44 | yes |
| top cue 2 | 7.175 | 11.41 | yes |
| top cue 3 | 13.375 | 9.62 | yes |
| top cue 4 | 19.375 | 8.2 | yes |
| top cue 5 | 25.875 | 7.63 | yes |
| top cue 6 | 31.875 | 7.44 | yes |
| top cue 7 | 37.875 | 7.79 | yes |
| top cue 8 | 43.625 | 11.39 | yes |
| top cue 9 | 50.25 | 7.35 | yes |
| top cue 10 | 57.25 | 15.24 | yes |
| top gap 10 | 54.25 | 0.0 | yes |
| bottom cue 1 | 5.35 | 5.84 | yes |
| bottom cue 2 | 27.75 | 6.09 | yes |
| bottom cue 3 | 43.5 | 15.31 | yes |
| bottom cue 4 | 50.25 | 16.43 | yes |
| bottom gap 2 | 13.25 | 0.06 | yes |
| bottom gap 3 | 40.25 | 0.02 | yes |
| bottom gap 4 | 46.25 | 0.01 | yes |
| bottom gap 5 | 57.0 | 0.0 | yes |

Bands (decision 0010): share of 0..54 s with text, minimum 0.7.

| version | band | cover | min |
|---|---|---|---|
| 9x16 | top | 0.961 | 0.7 |
| 9x16 | bottom | 0.857 | 0.7 |

Text contrast (WCAG, text #FFF8E7 over the clean master inside each text box), minimum 4.5.

| band | t (s) | contrast |
|---|---|---|
| top | 1.81 | 13.72 |
| top | 7.175 | 18.04 |
| top | 13.375 | 19.83 |
| top | 19.375 | 19.83 |
| top | 25.875 | 10.95 |
| top | 31.875 | 9.13 |
| top | 37.875 | 6.3 |
| top | 43.625 | 19.83 |
| top | 50.25 | 19.83 |
| top | 57.25 | 19.83 |
| bottom | 5.35 | 19.72 |
| bottom | 5.35 | 19.19 |
| bottom | 27.75 | 19.83 |
| bottom | 27.75 | 19.83 |
| bottom | 43.5 | 19.62 |
| bottom | 43.5 | 19.83 |
| bottom | 50.25 | 19.74 |
| bottom | 50.25 | 19.83 |
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

<!-- detail:short-9x16 -->
### short-9x16 detail

Video h264 High yuv420p 24.0 fps, 18.583 s; audio aac 48000 Hz 2 ch, 18.6 s. Silences over the limit in the opening seconds: 0. Failed limits: none.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| cue 1 | 1.7 | 10.62 | yes |
| cue 2 | 5.4 | 13.56 | yes |
| cue 3 | 8.8 | 15.45 | yes |
| cue 4 | 11.45 | 10.29 | yes |
| gap 2 | 3.5 | 0.17 | yes |
| gap 3 | 7.2 | 0.1 | yes |
| gap 4 | 10.35 | 0.25 | yes |
| gap 5 | 15.5 | 0.04 | yes |
<!-- /detail:short-9x16 -->

## Narration mix

| version | voice_rms_db | bed_under_voice_db | gap_db | bed_outside_change_db |
|---|---|---|---|---|
| preview-16x9 | -16.0 | -28.97 | 12.97 | 0.0 |
| 16x9 | -16.0 | -28.97 | 12.97 | 0.0 |
| 9x16 | -16.0 | -28.97 | 12.97 | 0.0 |

<!-- detail:16x9-tanpa-suara -->
### 16x9-tanpa-suara detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| cue 1 | 1.81 | 7.78 | yes |
| cue 2 | 5.09 | 9.89 | yes |
| cue 3 | 12.25 | 8.23 | yes |
| cue 4 | 17.21 | 7.27 | yes |
| cue 5 | 24.33 | 9.2 | yes |
| cue 6 | 30.25 | 7.94 | yes |
| cue 7 | 36.13 | 8.53 | yes |
| cue 8 | 43.09 | 10.28 | yes |
| cue 9 | 47.75 | 6.87 | yes |
| cue 10 | 56.75 | 15.77 | yes |
| gap 3 | 8.79 | 0.64 | yes |
| gap 4 | 14.75 | 0.89 | yes |
| gap 5 | 20.71 | 0.79 | yes |
| gap 6 | 27.33 | 0.48 | yes |
| gap 7 | 33.25 | 0.66 | yes |
| gap 8 | 39.13 | 0.68 | yes |
| gap 9 | 45.84 | 0.64 | yes |
| gap 10 | 51.75 | 0.6 | yes |
| gap 11 | 59.5 | 0.13 | yes |
<!-- /detail:16x9-tanpa-suara -->

<!-- detail:9x16-tanpa-suara -->
### 9x16-tanpa-suara detail

Video h264 High yuv420p 24.0 fps, 60.0 s; audio aac 48000 Hz 2 ch, 60.0 s. Silences over the limit in the opening seconds: 0. Failed limits: none.

| sample | t (s) | caption band diff | pass |
|---|---|---|---|
| top cue 1 | 1.81 | 7.44 | yes |
| top cue 2 | 7.175 | 11.41 | yes |
| top cue 3 | 13.375 | 9.62 | yes |
| top cue 4 | 19.375 | 8.2 | yes |
| top cue 5 | 25.875 | 7.63 | yes |
| top cue 6 | 31.875 | 7.44 | yes |
| top cue 7 | 37.875 | 7.79 | yes |
| top cue 8 | 43.625 | 11.39 | yes |
| top cue 9 | 50.25 | 7.35 | yes |
| top cue 10 | 57.25 | 15.24 | yes |
| top gap 10 | 54.25 | 0.0 | yes |
| bottom cue 1 | 5.35 | 5.84 | yes |
| bottom cue 2 | 27.75 | 6.09 | yes |
| bottom cue 3 | 43.5 | 15.31 | yes |
| bottom cue 4 | 50.25 | 16.43 | yes |
| bottom gap 2 | 13.25 | 0.06 | yes |
| bottom gap 3 | 40.25 | 0.02 | yes |
| bottom gap 4 | 46.25 | 0.01 | yes |
| bottom gap 5 | 57.0 | 0.0 | yes |

Bands (decision 0010): share of 0..54 s with text, minimum 0.7.

| version | band | cover | min |
|---|---|---|---|
| 9x16-tanpa-suara | top | 0.961 | 0.7 |
| 9x16-tanpa-suara | bottom | 0.857 | 0.7 |

Text contrast (WCAG, text #FFF8E7 over the clean master inside each text box), minimum 4.5.

| band | t (s) | contrast |
|---|---|---|
| top | 1.81 | 13.72 |
| top | 7.175 | 18.04 |
| top | 13.375 | 19.83 |
| top | 19.375 | 19.83 |
| top | 25.875 | 10.95 |
| top | 31.875 | 9.13 |
| top | 37.875 | 6.3 |
| top | 43.625 | 19.83 |
| top | 50.25 | 19.83 |
| top | 57.25 | 19.83 |
| bottom | 5.35 | 19.72 |
| bottom | 5.35 | 19.19 |
| bottom | 27.75 | 19.83 |
| bottom | 27.75 | 19.83 |
| bottom | 43.5 | 19.62 |
| bottom | 43.5 | 19.83 |
| bottom | 50.25 | 19.74 |
| bottom | 50.25 | 19.83 |
<!-- /detail:9x16-tanpa-suara -->
