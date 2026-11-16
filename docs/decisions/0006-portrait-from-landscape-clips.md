# 0006: 9:16 version from the landscape clips

Date: 2026-11-16. Status: accepted.

## Context
Decision 0001 planned a separate portrait generation per shot. Before the first portrait submit the live balance was 457
credits (ledger row `me_only`, 2026-11-16T12:02:11Z). One generation costs 9, and 457 - 9 = 448 is below the 450
reserve, so the credit guard refuses every portrait generation. The guard is a hard rule and is not bypassed.

## Decision
The 9:16 file is cut from the same accepted landscape clips, windows and audio mix as the 16:9 file
(`config/film.json` `edit.orientation.9x16 = landscape`, `edit.layout.9x16 = blur_fill`):

- the full landscape picture at the full 1080 px width (1080 x 608, ffmpeg lanczos from 1280 x 720), centred vertically;
- behind it, the same frame scaled to cover the portrait frame, blurred at a quarter of the output size and dimmed, so
  the frame has no black bars and the colour of the shot fills the screen;
- captions in the blurred area below the picture, inside the caption band (rows 68% to 80%), above the bottom 20% that
  phone app controls cover; the end card text is drawn over the dimmed picture in the middle.

A centre crop of the landscape clip was rejected: it keeps 405 of 1280 source columns (32% of the picture width), which
would drop the edges of every composed shot. The blur is a plain ffmpeg box blur, not a generative fill.

## Rollback
If portrait clips are generated later under the guard, set `edit.orientation.9x16` back to `portrait`, the layout to
`cover`, add the clips to `accepted.portrait` in `config/shots.json`, run `tools/mix.py --orientation portrait` and cut
again. The 16:9 file is unchanged by this decision.
