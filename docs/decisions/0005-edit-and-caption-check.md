# 0005: The edit and the caption check

Date: 2026-11-16. Status: accepted.

## Edit
`tools/edit.py` builds each version in two files. The clean master cuts every shot's `window_s` from its accepted clip,
scales it to the output size with ffmpeg lanczos (no AI upscaler), joins the shots in `film_s` order, holds the last
frame for the end card, dims it and draws the end card text from `config/film.json` `end_card`. The final file burns
the captions into the clean master and adds the audio mix after two-pass loudnorm (linear mode) to -14 LUFS with a
true peak target 0.5 dB under the -1 dBTP limit, so AAC encoding cannot push it over. Hard cuts between shots; the film
fades to black over its last second. The plan refuses shots that leave a gap or do not end where the end card starts.

## Caption check
Proof that every caption is burned at its time, without reading text by machine: at the middle of each cue the mean
absolute luma difference between the clean master and the final file, inside the caption band, must be above
`measure.in_cue_min` (4.0); at the middle of each gap between cues it must be below `measure.out_cue_max` (1.5). The
clean master and the final file are separate H.264 encodes, so the gaps are not exactly 0; the measured gap noise is
0.1 to 0.8. A band over the bottom 28% of the frame diluted one cue to 4.04, too close to the limit; the band now covers
rows 79% to 95% of the height, where the 16:9 captions sit (weakest cue 6.58). The 9:16 band (rows 68% to 80%) was
measured when that version was cut: weakest cue 9.78, largest gap 0.24. A person reads one frame per cue (`docs/frames/<version>-cue-NN.jpg`).

## Caption size for 9:16
At 64 px and 26 characters per line the closing caption needed three lines and a line would have run past the frame
(DejaVu Sans Bold averages 0.58 em per character). 9:16 captions are 56 px at up to 28 characters; a unit test keeps
characters x size x 0.6 inside the frame width less the side margins.

## Rollback
`git revert` the commit; the clips, mix and config are unchanged by the edit. Thresholds and the band live in
`config/film.json` `measure`.
