# 0013: Share button and the fee linked to its transaction

Date: 2026-11-19. Status: accepted.

## Context
The page is where viewers arrive from a shared link. It had no way to pass the link on, and the fee sentence
("219 satoshis") asked the reader to trust it. The transaction is public, so the reader can check it.

## Decision
- Share: one button under the players. `navigator.share({title, text, url})` opens the phone's own share sheet;
  closing the sheet (`AbortError`) does nothing. A browser without it (or a sheet that fails) gets a small panel:
  the page URL, a Copy link button with a `role=status` message, and links to X, WhatsApp and Telegram. The panel
  links are built by `tools/site.py` from `config/site.json` `share.targets` with the text and URL encoded; the URL
  is the canonical URL of the page language (`/` or `/ms/`). The share text is a sourced claim (`copy_facts`,
  `fee-usd`). No share library, no third party script, no tracking: three intent URLs do not need one.
  `share.enabled: false` removes the button and its script.
- Fee link: copy may wrap words in `[[fee]]...[[/fee]]`. `config/site.json` `link_marks.fee` names the link
  (`links.fee_tx`), a screen reader label from the language file and the only copy key allowed to carry the mark
  (`facts.fee`). The copy is HTML escaped first; the marks are swapped for the link afterwards. The build stops
  when a mark is in another key, is unbalanced, or when the link does not carry the transaction id written in the
  `fee-tx` row of docs/FACTS.md.
- Explorer, measured on 2026-11-19 from the host in Chromium (a data centre address):

  | explorer | result |
  |---|---|
  | blockchair.com | 401, "Access to blockchair.com is forbidden" |
  | explorer.bitcoinunlimited.info | 403, security verification page |
  | 3xpl.com | 429 status, page shows the txid and 0.00000219 BCH, fee in USD rounded to 0.00 |
  | bchexplorer.info | 200, shows the txid, block time, size 219 bytes and "Fee 0.00000219 BCH (219 sats)" |

  `bchexplorer.info/tx/<txid>` is used: it opens without a check and states the fee in satoshis, as the page does.
  A home connection may reach the others; the choice is one config value.

## Rollback
`share.enabled: false`; remove the marks from `facts.fee` (the build then shows plain text); or point
`links.fee_tx` at another explorer page that carries the same txid. `deploy/deploy.sh --rollback` for the live page.
