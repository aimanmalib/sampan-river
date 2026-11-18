# 0008: Vertical short of 15 to 20 seconds

Date: 2026-11-18. Status: accepted.

## Context
Short-video feeds favour clips under 20 seconds. The 60 second film exists in 9:16 (decision 0006, `blur_fill` kept by
decision 0007). A short version must use only footage already in the film (no new clips, no new music), carry its own
captions with a hook in the first 3 seconds, and meet the same sound limits as the film: -14 LUFS within 1 LU, true
peak at or below -1 dBTP, zero words from the speech check.

## What was built
- `config/short.json`: four segments of the film timeline in film seconds, the crossfade length, the fade out and the
  length limits (15 to 20 s).
- `config/captions.short.en.json`: four cues in short seconds. Every factual cue carries a `fact` id from `docs/FACTS.md`.
- `tools/short.py`: cuts the segments from the 9:16 clean master (so the layout and the end card are the film's own),
  joins them with `xfade`; cuts the same segments from the film mix and joins them with `acrossfade` of the same length,
  so picture and sound stay in step; fades the sound out over the last second; burns the captions with the 9:16 caption
  style; two-pass loudnorm as in `tools/edit.py`.
- `tools/measure.py short-9x16`: the film checks (size, frame rate, length, loudness, true peak, silence, speech, caption
  pixel check) against the short's own length and captions.

## Segments chosen
| film seconds | short seconds | picture | caption | why |
|---|---|---|---|---|
| 0.0 to 3.8 | 0.0 to 3.8 | toll bridge, queue, coin box | Sending $5 should not cost $5. | the hook: the problem in one line |
| 23.5 to 27.5 | 3.4 to 7.4 | the rower and the dollar coin in the boat | A digital dollar on Bitcoin Cash. (`pusd-token`) | the coin, clearly visible |
| 42.0 to 48.0 | 7.0 to 13.0 | the hand-over at the far bank | The fare for a real transfer: 219 satoshis. (`fee-tx`), Less than a tenth of a cent. (`fee-usd`) | the fare, the point of the film |
| 54.0 to 60.0 | 12.6 to 18.6 | end card: "Bitcoin Cash", "Get a wallet: bitcoincash.org" | none | the call to action |

Crossfade 0.4 s at each of the three joins; length 3.8 + 4.0 + 6.0 + 6.0 - 3 x 0.4 = 18.6 s.

## Measurement
`docs/MEASURED.md` row `short-9x16`: 1080 x 1920, 24 fps, 18.6 s, audio present, -14.0 LUFS, true peak -3.2 dBTP, speech
check 0 words, captions 4/4 with every gap below the limit. Frames `docs/frames/short-9x16-cue-01..04.jpg` and
`short-9x16-endcard.jpg` were read: each caption is complete under the picture and does not cover the coin; the end card
shows both lines in full.

## Rollback or change
Edit the segments or cues in the two config files and run `tools/short.py` then `tools/measure.py short-9x16 --write`.
The film files are not touched by this tool.
