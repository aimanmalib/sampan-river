# 0015: Banner note, first commit and repository links

Date: 2026-11-20. Status: accepted.

## Context
The organiser asks each entry to show, near the top, what was built during the event. This film's repository
starts on 16 November 2026, after building opened on 14 November 2026 14:00 UTC, so the page can say so. The
repository is still private: a link to it, or to its first commit, answers 404 to a visitor.

## Decision
- `config/site.json` `banner` holds `event_start_utc`, `first_commit` (`sha`, `date_utc`), `repo_check`,
  `repo_api` and `deck` (language code to a PDF path, empty for none). `tools/banner.py` reads it; the build stops
  when the first commit is not after the event start, the sha is not a full commit id or `repo_check` is unknown.
- The note is always shown, in English and Malay: `banner.note` in `site/lang/*.json` with `{first_commit}`
  (day month year) and `{event_start}` (day month) filled from config, month names from `banner.months`. It is a
  sourced claim (`copy_facts`: `event-start`, `first-commit` in docs/FACTS.md).
- `repo_check`: `on` shows the repository link and the first commit link; `off` leaves them out; `auto` writes
  them with `hidden` and `site/repo.js` shows them once GitHub lists the repository as public. The page then
  needs no new deploy when the owner makes the repository public.
- The check asks `https://api.github.com/users/<owner>/repos?sort=created&per_page=100` rather than
  `/repos/<owner>/<name>`. Both tell public from private, but the single repository URL answers 404 while the
  repository is private and browsers write that failed request to the console as an error on every visit; the list
  answers 200 and simply does not include a private repository. `repo_api` is config, so the single URL can come
  back without a code change. The request sends no cookies and no referrer. An error or a rate limit (60 an hour
  per visitor address) leaves the links hidden.
- CSP: `connect-src 'self' https://api.github.com`, nothing else added.
- Deck: when `deck.<lang>` names a file, the build copies it under `/deck/` and links it in the banner; empty
  means no link (the deck is a later step and may be skipped).

## Measured (2026-11-20, local container with the real nginx.conf)
WebKit iPhone 13 and Chromium 320 px and desktop, `/` and `/ms/`: the request to the GitHub API is made and
allowed by the CSP, the links stay hidden, the console is empty; with the API answer replaced by a list holding
the repository, all four gated elements show. No sideways scroll; the 9:16 player keeps at least 71 % of its
height on the first phone screen with the links shown (check limit 60 %).

## Way back
`repo_check: "off"` or `"on"` in config, or `deploy/deploy.sh --rollback`.
