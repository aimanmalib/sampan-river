# 0014: Vertical share image and link preview tags

Date: 2026-11-19. Status: accepted.

## Context
Most viewers arrive from a link shared in a chat or a feed. The page's `og:image` was the 1280 x 720 landscape
thumbnail, which a phone feed shows as a small strip. A taller image fills more of the screen, but each app crops it
differently: WhatsApp shows a square from the centre of a portrait image, Facebook and Telegram cut to about
1.91:1, and X cuts a large card to about 1.91:1 as well.

## Decision
- `og:image` is a 1080 x 1350 (4:5) JPEG, `docs/frames/og-vertical.jpg`, written by `tools/og.py` from one committed
  9:16 cue frame (`docs/frames/9x16-cue-05.jpg`). The 16:9 picture band of that frame is cropped and scaled with
  lanczos onto a blurred copy of the same frame. No frame is generated and no image model is used.
- The text is the film's own: the title from `config/film.json`, the hook caption `film-05` ("A digital dollar on
  Bitcoin Cash.", fact `pusd-token`) and the 9:16 band with fact `fee-tx` ("219 sats", "the real fare"), plus the
  domain. It is drawn by ffmpeg's `ass` filter in the caption font and colours.
- Layout rule, checked by `tools/og.py` before it runs ffmpeg: the title, the hook, the rower and the coin sit inside
  the centre 1.91:1 box (so a wide preview keeps the title too); the domain and the fare figure are added inside the
  centre 1:1 box. `--crops` writes those two crops
  (`docs/frames/og-crop-1x1.jpg`, `og-crop-191.jpg`) so they can be read.
- `twitter:image` stays the landscape thumbnail, because X crops a portrait image to 1.91:1 itself.
- `og:video` (with `secure_url`, `type`, `width`, `height`) names the narrated 9:16 file the first player serves.
- Alt text for both images is in `site/lang/*.json` (`meta.og_alt`, `meta.twitter_alt`), English and Malay.
- `tools/site.py` stops the build when `og_image` is over `og_image_max_bytes`, or, while `og_image_portrait` is
  true, when it is not taller than it is wide.

## Read in the images (2026-11-19, second layout)
The first layout put the title above the 1.91:1 box, so a wide preview showed only the hook and the picture. The
title now sits at the top of that box and the picture band is smaller (356 px high instead of 446).
- `og-vertical.jpg` (84,620 bytes): blurred warm brown background; the domain in small letters high up; "The River
  Fare" in large cream letters with a dark outline; "A digital dollar on / Bitcoin Cash." in two smaller lines; then
  the picture band: the paper rower in a conical hat holding an oar at the stern of a folded paper boat, the gold
  coin with a raised "1" in the bow on the right; under it "219 sats" large and "the real fare" small. No text
  touches the rower, the oar or the coin.
- `og-crop-1x1.jpg` (45,455 bytes): domain, title, hook, rower, boat, coin, "219 sats" and "the real fare".
- `og-crop-191.jpg` (52,687 bytes): title at the top, the two hook lines, then the rower, the boat and the coin;
  the figure is cut.

## Way back
Config only: set `og_image` in `config/site.json` back to `docs/frames/thumbnail.jpg` and `og_image_portrait` to
false, then rebuild; or roll the page back to the previous tag.
