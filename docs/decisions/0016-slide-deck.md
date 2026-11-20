# 0016: Slide deck, one PDF per language

Date: 2026-11-20. Status: accepted.

## Context
The organiser's banner asks for a deck next to the repository and the prize address. The page already says
everything the deck needs: the story, the measured fee, how the film was made and where AI was used, and the
address. A second copy of that text would drift from the page.

## Decision
- Five 1920 x 1080 slides: title and one sentence with the thumbnail; the story (toll bridge and sampan frames);
  the real numbers (219 sats, the transaction id linked to the explorer of decision 0013, the day's price, the
  "one measured transfer" note); how it was made, using the page's own `ai.*` sentences; watch and share with the
  page address, the prize address and the banner note of decision 0015.
- Text lives in `site/lang/{en,ms}.json` under `deck.*`, so the page's checks apply: key parity, banned words,
  em dashes, and every claim key mapped to a `docs/FACTS.md` row in `config/site.json` `copy_facts`.
- `tools/deck.py` fills `site/deck/deck.html` with the page renderer, embeds committed film frames as data URIs
  (no new picture is generated), checks in Chromium that no slide overflows or runs into its footer, screenshots
  every slide for review, and prints `site/deck/the-river-fare-{en,ms}.pdf`. Colours and fonts are the page's
  `:root` tokens read from `site/style.css`.
- `site/deck/deck.sha256` records, per language, the sha256 of the HTML that was printed and of the PDF.
  `tools/deck.py --check` and `tests/test_deck.py` render the HTML again: new text, a new address or a new
  frame without a new print fails, as does a PDF replaced by hand, a file that is not a PDF, a PDF over
  `deck.max_bytes`, a slide 5 without the prize address, or a banned word.
- `config/site.json` `banner.deck` names the two PDFs; `tools/site.py` copies them under `/deck/` and links
  each page's own language.

## Consequences
- Changing any deck sentence, the address or a frame means running `python3 tools/deck.py --shots <folder>`
  (Playwright Chromium) and committing the new PDFs and stamp.
- Undo: set `banner.deck` to empty strings and rebuild; the page drops the link.
