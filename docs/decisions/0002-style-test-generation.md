# 0002: Style locked after one test generation

Date: 2026-11-16. Status: accepted.

## Test
One landscape generation of the opening shot `toll-bridge` with the prompt built from `config/shots.json`
(shot action + `style` + `exclude`). Ledger row: `toll-bridge-l-45721e195c36482d`, 9 credits, status `done`,
sha256 `90a69f757bba7bc953352ded3a7ad5fd1dce1583d8a17f8ad3981db76b1e846e`.

Measured on the raw clip: 1280x720, 24 fps, H.264, AAC stereo 32 kHz, 30 s. Integrated loudness -33.9 LUFS
(quiet ambience; the final mix is normalised later). Local speech check (`tools/transcribe.py`, faster-whisper
`small.en`): 0 words.

## What the frames show (docs/frames/test-*.jpg, read one by one)
- 01 s: an empty grey card bridge with two gate openings, paper mountains and cotton-wool clouds behind. No figures yet.
- 03 s: travellers in conical paper hats enter the bridge; a tall box-shaped toll keeper stands next to a chest of gold coins.
- 05 s and 10 s: a queue of hatted paper travellers seen from behind walks towards the keeper and the full coin chest.
  Warm late-afternoon light, shallow depth of field.
- 15 s: the camera moves along the arched bridge; a teal painted river appears below.
- 21 s: on a cotton-wool bank under the bridge a folded paper rower with a conical hat stands by a single gold coin
  next to an origami paper boat.
- 27 s: the rower pushes the boat towards the water; a small gold glint sits in the bow.

In every frame: no text, letters, numbers, signs or logos; no faces (the keeper is a plain folded box shape, travellers
and rower are hats and paper bodies). The look is a folded paper and card miniature with a painted river; the
watercolour wash is mostly in the water rather than the banks. That is acceptable for the story and it keeps the two
paper worlds coherent.

## Decision
Pass. The `style` and `exclude` blocks in `config/shots.json` are locked (`style_locked`); later shots reuse them
unchanged. No retry was spent.

## Notes for the edit
- The first 2 s are an empty bridge, a weak hook. The opening window should start near 2.5 s, where travellers and
  the coin chest are already in frame, so the hook caption lands on the toll scene.
- The keeper scooping coins from each traveller is implied by the queue and the full chest rather than shown as a
  clear gesture.
- The coin in the bow is small at 720p; the crossing shot prompt keeps the coin as the subject.

## Rollback
Revert this decision and remove `style_locked`; the next generation would then use whatever style text replaces it.
