# Shots

Every generated clip, with the decision and the seconds used in the edit. Source of the windows: `config/shots.json`
(`window_s`, `film_s`, `accepted`). Clips are 1280x720, 24 fps, 30 s, with an AAC audio track; raw files stay out of git
and are identified by the sha256 in `log/generations.jsonl`. Frames under `docs/frames/` were read one by one.

## Landscape

| Clip | Shot | Decision | Window used | Film seconds |
|---|---|---|---|---|
| toll-bridge-L1.mp4 | toll-bridge | accepted, window 5 to 27 s | 5 to 27 s | 0 to 22 s |
| crossing-L1.mp4 | crossing | accepted, window 4 to 22 s | 4 to 22 s | 22 to 40 s |
| green-bank-L1.mp4 | green-bank | accepted, window 8 to 22 s | 8 to 22 s | 40 to 54 s |

One `green-bank` submit failed at the provider (render queue full) and was refunded; the ledger row shows
`failed`, `refunded: true`, 0 credits. The second submit with a new idempotency key succeeded.

### toll-bridge-L1.mp4
Accepted in decision 0002. The window now starts at 5 s instead of 2.5 s: the queue of travellers and the full coin chest
are already in frame for the hook, and ending at 27 s keeps the rower pushing the boat out, which the storyboard places
at film 16 to 22 s.

### crossing-L1.mp4 (frames `docs/frames/crossing-L1-*.jpg`)
- 01 s: almost black, a warm out-of-focus edge; the clip fades in.
- 05 s: close shot of a folded brown paper boat; the rower is a flat dark paper silhouette holding a long oar; a gold coin
  stands in the bow.
- 10 s to 29 s: wider shot of the same boat crossing a pale paper river at dusk, layered folded paper hills behind; the
  coin keeps its size and shine in the bow; a soft green glow grows in the sky over the far bank from 15 s; paper reeds
  appear at the right from 20 s.
- No letters, signs, logos or faces. The coin face shows a single embossed numeral "1". It reads as a one dollar coin,
  which is the point of the shot, so it is kept; captions never depend on it.
- Window 4 to 22 s skips the dark fade-in.

### green-bank-L1.mp4 (frames `docs/frames/green-bank-L1-*.jpg`)
- 01 s: night; a white folded paper boat with the hatted rower drifts towards a paper jetty where two hatted figures
  wait; a small paper bowl sits on the jetty edge.
- 05 s: a green paper lantern on a pole lights the boat; the rower holds a gold coin out.
- 10 s and 15 s: the coin passes from the rower to the figure on the jetty, next to the bowl.
- 20 s to 29 s: the camera rises to a wide shot of many small lantern-lit paper boats on a dark teal river under
  folded paper mountains.
- No letters, signs, logos or faces. The grain of rice is too small to see; the caption carries the fare.
- Window 8 to 22 s covers the hand-over and the rise to the many boats.

## Speech check
`tools/transcribe.py` (faster-whisper `small.en`) over the full 30 s clips returns one short phrase per clip
("I'll see you in the next video.", "I'll see you next time."): a single 0 to 7 s segment with no-speech probability
0.49 to 0.58 and average log probability below -1.2, the known pattern of the model inventing outro phrases on ambient
sound. With voice activity detection the model finds nothing in `crossing` and invents "Thanks for watching!" at 0.3 s in
`green-bank`, before the used window. Transcribing only the used windows (4 to 22 s and 8 to 22 s)
returns 0 words for both clips. The binding check is the zero-word transcription of the final mixed audio (decision 0001).

## Portrait
Generated in the 9:16 step.
