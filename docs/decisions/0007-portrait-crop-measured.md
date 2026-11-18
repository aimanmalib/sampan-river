# 0007: 9:16 picture size, crop measured against blur_fill

Date: 2026-11-18. Status: accepted.

## Context
In the 9:16 file from decision 0006 the landscape picture is 1080 x 608, about a third of the portrait frame. A larger
picture needs a crop of the landscape clip: a 4:5 box (576 x 720 source pixels, shown at 1080 x 1350) or a 1:1 box
(720 x 720, shown at 1080 x 1080). Both are scaled up with ffmpeg lanczos (1.875x and 1.5x), while `blur_fill` scales
down (0.84x). The rule set before measuring: take the largest crop whose sharpness is at least 0.55 of `blur_fill`
(`measure.sharpness.min_ratio`) and whose frames show the whole subject; if none passes, keep `blur_fill`.

## What was built
- `tools/layout.py`: the `crop_fill` layout. A `crop_aspect` box that follows the subject through per-clip keyframes
  (`edit.layout.9x16.centre_x`, box centre in source pixels at seconds from the window start, linear between keys),
  scaled to full width over the same blurred background as `blur_fill`. A box that leaves the source frame is an error.
- `tools/sharpness.py`: variance of the Laplacian of the luma for the same scene region (a 4:5 box at the keyframed
  centre) shown at each layout's size, at 25, 50 and 75 percent of each shot window (9 samples). Same region in every
  layout, so the number compares scaling, not content. Table: `docs/MEASURED.md` section "Sharpness (9:16 layouts)".

## Measurement
Mean ratio to `blur_fill`: 4:5 = 0.103, 1:1 = 0.196, limit 0.55. Per sample the 1:1 ratio runs from 0.184 to 0.212
and the 4:5 ratio from 0.095 to 0.117. The metric counts detail per screen pixel: magnifying a 720 px clip spreads each edge over
more pixels, so the crop looks softer on the phone even though it shows the same source detail. No crop passes.

Frames read before measuring (contact sheets of each shot window, six frames per shot, with a 128 px column grid):
- toll-bridge: the subject moves from the toll keeper and the coin box on the right (source x about 850 to 1200 at the
  start of the window) to the rower and boat on the left (about 180 to 780 at the end); a fixed crop cannot hold both,
  a keyframed pan can.
- crossing: near 7.6 s in the clip the boat spans about 1050 source pixels, the rower at about 300 to 520 and the coin
  at about 950 to 1110; neither a 4:5 nor a 1:1 box holds rower and coin together at that moment.
- green-bank: the hand-over (rower, coin, receiver) sits within source x about 460 to 820 for most of the window, which
  a 1:1 box holds.

## Decision
Keep `edit.layout.9x16.mode = blur_fill`. The 9:16 file was cut again with this layout so that it carries the current
captions and end card; the 16:9 filter graph is unchanged (checked equal to the graph of the previous edit code, so the
16:9 file was not cut again and its sha256 is the same).

## Rollback or change
To use a crop later: set `edit.layout.9x16.mode` to `crop_fill`, `crop_aspect` to `[1, 1]` or `[4, 5]`, check
`picture_y_ratio` keeps the picture above the caption band (`tests/test_layout.py` checks this for the committed
config; a 4:5 picture at 1350 px cannot sit above the current band and needs the band moved), then run
`tools/edit.py 9x16` and `tools/measure.py 9x16 --write`. The `centre_x` keyframes for the three accepted clips are kept
in the config for that purpose.
