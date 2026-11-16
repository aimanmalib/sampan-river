# 0001: Story, look and credit rules

Date: 2026-11-16. Status: accepted; the 9:16 film is cut from the landscape clips instead of portrait generations (decision 0006).

## Story and look
A wordless 60 s fable: a toll bridge takes a big coin from every traveller; a small rower carries one gold coin across a river
to a green-lit Bitcoin Cash bank instead, arriving with the coin unchanged and paying a fare of one grain of rice.
Look: folded paper diorama with watercolour washes. Figures are silhouettes seen from behind with conical hats, so the model
never has to draw detailed or photorealistic faces. All on-screen text (captions, end card) is drawn by code; prompts forbid
generated text, logos, speech and music.

## Clips
VE Studio text-to-video, 30 s fixed clips: landscape 1280x720 and portrait 720x1280, 24 fps, with ambient audio. The 9:16 film
uses its own portrait generations from the same shot prompts, not a centre crop of the landscape clip (a crop would leave only
405 source pixels across). The 1080p outputs are upscaled with ffmpeg lanczos; no AI upscaler.

## Credit rules (hard)
- Before every submit: `GET /v1/me`. Submit only if balance - cost >= `reserve_ai_film` (450) AND Media credits already spent
  + cost <= `media_cap` (120). Values live in `config/film.json`; tests fail if the guard weakens.
- The ledger row (idempotency key, `me_before`, cost) is written before the request; the outcome updates the same row.
- One generation at a time. A timeout or `409 in_progress` is retried with the same idempotency key only.
- A refused guard stops the work; it is not retried with another key.
- Default budget: 1 test + 3 landscape (+ up to 3 retries) + 3 portrait (+ up to 2 retries) = at most 13 generations = 117 credits.

## Sound
Original theme synthesised by code (numpy, deterministic, no samples). Ambient river sound comes from the generated clips.
No voice. The final audio is transcribed locally with faster-whisper `small.en`; it must contain zero words.

## Fallbacks
- Guard refuses before all landscape clips exist: shorten the 16:9 film to the clips available (at least 45 s from two clips).
- Portrait generations unavailable: build 9:16 from the 16:9 master (blurred fill of the same frame behind the full picture),
  recorded in a new decision.
- A fact that cannot be sourced is removed from the captions (`docs/FACTS.md`).
