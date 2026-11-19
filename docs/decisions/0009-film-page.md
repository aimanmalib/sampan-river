# 0009: A small live page for the film

Date: 2026-11-19. Status: accepted.

## Context
Judges and viewers need one link that plays the film, shows the prize address and says how AI was used, in English and
Malay. The page must serve only the measured files (docs/MEASURED.md), make no claim without a source in
docs/FACTS.md, and stay quiet about the source repository and the video upload until those exist.

## What was built
- `config/site.json`: domain, languages, prize address, which video version and file to serve, posters, links, the
  `youtube_url` and `repo_public` switches, the copy-to-fact map (`copy_facts`), words that are never used, and the words
  that mark a sentence as a claim (`claim_words`).
- `site/index.html` (one template), `site/style.css` (paper, ink and brass from the film; system fonts; no blur or
  animated filters), `site/copy.js` (copy button for the address), `site/lang/en.json` and `site/lang/ms.json` (same keys).
- `tools/site.py`: standard library only. Checks the copy (same keys in both languages, no banned word or em dash, every
  sentence with a claim word mapped to fact ids that exist), copies each video only when its sha256 equals the MEASURED
  row for its version, names assets by content hash, writes `/` (English), `/ms/` (Malay), `robots.txt` (allows
  previews) and `healthz`. The YouTube and repository links are rendered only when `youtube_url` is set or
  `repo_public` is true.
- `deploy/`: `Dockerfile` (nginx 1.27 alpine, unprivileged, read-only root), `nginx.conf` (all response headers in the
  one server block, cache lifetimes by path through a `map`, byte ranges for the videos), `compose.yaml` (one container,
  0.5 CPU, 64 MB, project-prefixed name), `traefik.yaml.tmpl` (own router and certificate), `deploy.sh` (clean
  `git archive` build plus the videos from the host media folder, `--status`, `--rollback`, retried public health, browser
  check, automatic rollback), `check_page.py` (WebKit iPhone 13, Chromium desktop and 320 px: no sideways scroll, address
  and film on a phone's first screen, videos load, copy button answers, no console error).

## Choices
- Two videos: the 16:9 film (poster: the thumbnail) and the 18.6 s vertical cut (poster: its first caption frame). The
  60 s 9:16 version is not on the page; it is the same film in another frame.
- Content security policy is `default-src 'self'` with `style-src 'self' 'unsafe-inline'`. Without the inline allowance
  WebKit refused the stylesheet of its own video controls (console error on the iPhone 13 run, 2026-11-19), which could
  leave the player unstyled on iPhones. The page has no user input, so the allowance exposes nothing.
- The banner says "CashTokens address for prizes and EMBER2026 community votes". Fact `ember-vote`: the event Details
  page (dorahacks.io/hackathon/bchblaze2026/detail) lists Community Choice, 750 PUSD, for the project with the most
  EMBER2026 tokens, read on 2026-11-15. A re-fetch on 2026-11-19 was refused by the site's bot check (HTTP 405 on its API,
  a challenge page on the HTML), so the dated earlier reading is the source.
- No static site generator: two pages from one template do not need one.

## Measured (local, 2026-11-19)
Built from the media folder and served by `nginx:1.27-alpine` with `deploy/nginx.conf` on a local port: `/`, `/ms/`,
`/healthz`, `/robots.txt` 200; `/ms` 301 to `/ms/` (relative); 16:9 video with `Range: bytes=0-99` 206 with
`Content-Range: bytes 0-99/40077465`; HTML `Cache-Control: no-cache, no-transform`, videos `immutable`.
`deploy/check_page.py`: six runs (three browsers, two languages) all ok. Screenshots read: banner, title and film on
the first iPhone 13 screen in both languages; address wraps inside the banner at 320 px; sections spaced; vertical cut
beside its text on desktop and under it on a phone.

## Undo
`deploy/deploy.sh --rollback` returns the previous image. To remove the page: `docker compose -f deploy/compose.yaml
down`, delete the route file from the proxy's dynamic folder, and delete the DNS record.
