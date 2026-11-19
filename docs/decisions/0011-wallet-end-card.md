# 0011: End card names two wallet apps

Date: 2026-11-19. Status: accepted.

## Context
The end card said "Get a wallet: bitcoincash.org" (fact `wallet-link`). A viewer who wants to act on the film has to
open a second site and choose among many wallets there. Naming two wallet apps on the card gives a direct next step.

## Decision
- `config/film.json` `end_card.lines`: "Bitcoin Cash", "Get a wallet:", "Paytaca · Selene" (middle dot U+00B7, no
  long dash). The first line keeps the large size; the two others use the small size of each version.
- Each wallet name is backed by its own site, read on 2026-11-19 (docs/FACTS.md):
  - `wallet-paytaca`: `https://paytaca.com` (HTTP 200) heads its wallet section "Bitcoin Cash · Peer to peer" and
    lists "Wallet" for individuals.
  - `wallet-selene`: `https://selene.cash` (HTTP 200): "Selene Wallet is a fast, simple, secure wallet app for the
    Bitcoin Cash (BCH) cryptocurrency".
- The card says only that these are wallets. It claims no sponsorship, endorsement or PUSD support, because neither
  page says so.
- `end_card.line_facts` maps each line after the title to fact ids (a list). `wallet-link` stays in FACTS and on the
  film page.

## Tests
- Every end card line after the first has fact ids, and each id has a sourced row in docs/FACTS.md.
- A line naming a wallet that has a `wallet-<name>` fact must cite that fact (removing the Selene id fails the test).
- No long dash or exclamation mark on the card; every line fits the frame width of 16:9 and 9:16.

## If a source goes away
A wallet whose own page no longer says it is a Bitcoin Cash wallet is dropped from the card (and from FACTS); the
card falls back to "Get a wallet: bitcoincash.org" when neither can be confirmed. Rollback: `git revert` this change
and render again (no new clips).
