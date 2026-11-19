# 0010: Native vertical bands

Date: 2026-11-19. Status: accepted.

## Context
The 9:16 file shows the 16:9 picture at full width in the middle of the frame (decision 0006, `blur_fill`; decision
0007 measured that a narrower crop is too soft). Above and below the picture there were two blurred bands, empty except
for one caption line in the lower band. On a phone this reads as a letterboxed landscape video. The picture itself
does not change; the bands are made to carry the story.

## Decision
- Top band (`tools/bands.py`): the caption cues of `config/captions.en.json` (the same source as the SRT and the
  narration) drawn large (78 px DejaVu Sans Bold, at most 20 characters a line and 3 lines) in the middle of the band.
  On screen each cue stays until the next cue starts (less 0.25 s, at most 7.5 s), so the band does not go blank while
  the voice pauses. The SRT keeps the spoken times; only the burned 9:16 text is held.
- Bottom band: one large figure (190 px) with a small label (44 px) per span, from `config/bands.json`: "$5" while the
  hook speaks of sending $5, "$1" (fact `pusd-design`), "219 sats" (fact `fee-tx`), "< $0.001" (fact `fee-usd`).
  A figure with a digit or currency sign must name a fact in docs/FACTS.md; the one exception is a figure that appears
  in the unsourced hook cue. Nothing is drawn in the bands after the end card starts, except the closing caption.
- Background: still the blurred copy of the frame, never animated blur. It is darkened (`background_brightness`) until
  the cream text (#FFF8E7) measures a WCAG contrast of at least 4.5:1 over the clean master inside every text box.
- Style, sizes, positions and hold times live in `config/film.json` `captions.bands`; figures, labels, times and facts
  in `config/bands.json`. The landscape film is unchanged.

## Measured (tools/measure.py, docs/MEASURED.md)
- Pixel check per band: inside every span the final file differs from the clean master in that band; between spans
  it does not.
- `band_cover`: share of 0 to 54 s (end card start) with text in the band; at least 0.70 for each band.
- Contrast table: one row per text box (each held caption, each figure and each label).
- Before the render, the same layout was drawn on single frames of the clips at every text box time: at the old
  brightness -0.12 the worst box measured 2.31:1, at -0.30 it measured 4.79:1. The film uses -0.36 for margin.
- Render of 2026-11-19: cover 0.961 (top) and 0.857 (bottom), lowest contrast 6.3:1 (top band at 37.9 s), the pixel
  check passed in all 14 spans and every gap; frames `docs/frames/9x16-cue-*.jpg` read: captions in the top band, the
  figure and label in the bottom band, neither over the picture, the end card whole.

## Considered
- Auto-captioning templates for vertical video: they run outside the ffmpeg pipeline, cannot be tested here and do
  not take sourced figures. One small ASS writer is enough.
- A narrower crop of the picture to fill more height: rejected by measurement in decision 0007.

## Rollback
Remove `9x16` from `captions.bands` in `config/film.json`: the 9:16 file goes back to the single caption line, then
render again (same clips, no credits).

## The short (added with the short render)

The short reuses the 9:16 band style unchanged. Its bottom band rows are `config/bands.json` `short-9x16`, in short
seconds. `tools/short.py` `short_film` maps the film's end card start into short seconds (`to_short`: the second at
which that film second is shown after the crossfades), so the rule "no figure after the end card starts" and
`band_cover` apply to the short's own end card. The narration is placed over the short's cut bed, never cut from the
narrated film, and the silent copy is written in the same pass.
