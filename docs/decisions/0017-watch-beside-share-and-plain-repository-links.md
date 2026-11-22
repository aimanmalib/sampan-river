# 0017: Watch on YouTube beside Share, repository links in plain HTML

Date: 2026-11-22. Status: accepted.

## Context
The film is on YouTube (`youtube_url`, decision 0009). Its link sat under the description, below the 9:16 player,
so a phone visitor only found it after scrolling. The repository is now public (`gh repo view` reports
`"visibility":"PUBLIC"`), while the page still wrote the repository links hidden and asked the GitHub API from each
visitor's browser to show them (decision 0015), a request limited to 60 an hour per visitor address.

## Decision
- One row, `.actions`, holds Watch on YouTube (`a.watch[data-watch]`, `rel="noopener"`) and the Share block
  (decision 0013). It is the only YouTube link in the template. `youtube_url` empty leaves the link out; Share
  switched off leaves the link in; both off leave the row out (`actions` flag in `tools/site.py`).
- Watch is a secondary button: ink text and a 2 px ink border on a solid cream background, at least 44 px high.
  The solid background lets the browser check measure the text contrast from computed colours.
- On a wide screen the row stays under the players. On a phone (below 37.5rem) it moves between the title and the
  9:16 player with flex `order`, so both buttons are on the first screen. The 9:16 player height token on phones
  goes from 66svh to 60svh to pay for that row and keep `check.min_visible` (0.6) at 320 px wide.
- When the Share panel opens (no share sheet), the Share block takes a row of its own, so the panel never pushes
  the row wider than the screen.
- `banner.repo_check` is `on`: the repository and first commit links are plain HTML, without `hidden`, and
  `site/repo.js` is not loaded. The CSP keeps `connect-src https://api.github.com` so `auto` can come back
  through config alone.
- The template engine now resolves nested blocks: an outer block keeps its inner blocks for the next pass.

## Checks
- `deploy/check_page.py` (`watch_problems`): exactly one YouTube link; its href is `youtube_url`; at least 44 px;
  text contrast at least 4.5:1 from computed colours (a transparent background counts as 0); on the first iPhone 13
  screen; a repository link is shown when `repo_check` is `on`; no sideways scroll with the Share panel open.
- `tests/test_watch.py`: the build in both languages (one link, inside the row, before Share; none without a URL;
  kept without Share; no empty row; repository links without `hidden` and without `repo.js`), nested blocks, and
  each `watch_problems` fault named on a probe fixture.

## Measured (2026-11-22, local container with the real nginx.conf)
| run | 9:16 top / height / viewport | result |
|---|---|---|
| WebKit iPhone 13 EN | 342 / 398 / 664 | ok |
| WebKit iPhone 13 BM | 363 / 398 / 664 | ok |
| Chromium 1366 EN, BM | film first screen | ok |
| Chromium 320 EN, BM | 394 / 384 / 640 | ok |

Before the move, the iPhone 13 check reported "Watch on YouTube link is below the first screen" in both languages.

## Rollback
`banner.repo_check: "auto"` in config brings back the API check; `git revert` of the change restores the old row.
