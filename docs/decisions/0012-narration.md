# 0012: Narration in the maker's own cloned voice

Date: 2026-11-19. Status: accepted (takes generated 2026-11-19; the films are rendered with them in the next steps).

## Context
The maker asked for the film to be read aloud in their own voice. They already have an instant voice clone at
ElevenLabs. The film stays in English; the spoken words must be the words on screen, so a viewer with sound off and a
viewer with sound on get the same film.

## Script
- The script is the caption text (config/captions.en.json, config/captions.short.en.json). Each cue has an `id`
  (`film-01`..`film-10`, `short-01`..`short-04`).
- `spoken(text)` turns screen text into the words to say with `spoken_map` in config/voice.json ("$5" -> "five
  dollars", "219" -> "two hundred and nineteen"). A cue may carry `say`; it must normalise to the same words as the
  screen text (numbers and "$" amounts are compared as words), so the voice can never say something the screen does
  not show. A unit test holds every cue to this.

## Voice and requests
- Model, language and audio format: config/voice.json (`eleven_v3`, `en`, `mp3_44100_192`). The voice id and the API
  key come from the environment (`voice_env`, `key_env`); they are never written to a tracked file or the ledger.
- Endpoints: `POST /v1/text-to-speech/{voice_id}/with-timestamps` (audio plus character timings) and
  `GET /v1/user/subscription`. The client connects over IPv4 only.

## Guard and ledger
- Before every request: characters left on the account - characters of the request >= `reserve_chars`, and the
  ledger total + the request <= `char_budget`. Otherwise nothing is sent.
- `log/voice.jsonl` gets the row (`id`, `take`, `chars`, `hash`, `text_sha8`, `sub_left_before`, status `sent`)
  before the request; after it the same row becomes `done` with the sha256 of the audio, `duration_s` and
  `whisper_match`, or `failed` with the HTTP status. A network error leaves the row `sent` (the characters may have
  been charged), and a `sent` row blocks a new request for that line until someone looks at it.
- Cache: one file per take, named by cue id, a hash of text + voice + model settings, and take number. A line whose
  hash already has a passing take is never sent again; `eleven_v3` does not repeat itself, so a chosen take is kept.
  A take passes when its whisper match (words of the line heard in order / words of the line) is at least
  `match_min`; otherwise another take, up to `max_takes`.
- Audio files stay in the untracked media folder: they are the maker's voice.

## Placement and captions
- A line starts speaking at its cue start + `lead_s`. Its window ends `min_gap_s` before the next cue (the last cue:
  the end of the version). Too long: ffmpeg `atempo` up to `max_tempo`; still too long: another take or a shorter
  caption (facts unchanged); otherwise that one line is held back and the rest still speak.
- Caption times then follow the voice (start = voice start - `lead_s`, end = voice end + `tail_s`, long enough for
  `min_cue_s` and `srt.max_cps`, never past the next cue). The burned captions, the 9:16 bands and the SRT all read
  these times. The SRT is held to the `srt` limits: 42 characters per line, 2 lines, 20 characters per second, 1 s
  minimum, no overlap.
- The short is narrated on its own cut bed, in short seconds. The narrated film is never cut, because the cuts would
  split lines.

## Mix
- Each line is set to `voice_rms_dbfs`. The bed (music and river ambience, decision 0004) is multiplied by a gain
  envelope: -`duck_db` inside each voice span, linear ramps of `ramp_s` outside it, 1 elsewhere. The sum goes through
  the existing limiter, then the two-pass loudnorm of the edit.
- ffmpeg `sidechaincompress` was considered and not used: its attack and release follow the signal, which makes the
  result harder to test and to measure, while the span of every line is already known.
- Measured in docs/MEASURED.md "Narration mix": voice level, bed level under the voice, the gap between them (at
  least 10 dB) and the bed level change further than `ramp_s` from any line (within 0.5 dB, so the music is not
  turned down where nobody speaks).

## Speech check
- Narrated versions are checked the other way round from decision 0004: whisper (with voice activity detection) on
  the final file must hear the script, `speech_match` >= `audio.speech_check.match_min` (0.85).
- Every narrated render also writes the same picture without the voice (`-c:v copy`, the undimmed bed through the
  same loudnorm), named with `audio.speech_check.silent_suffix`. It is measured as a silent film (0 words).
- `tools/edit.py` builds the narrated mix (`tools/narrate.py`), renders the narrated file and the silent copy in one
  pass and leaves the mix stats in `narration-<version>.json`; `tools/measure.py --write` puts them in the "Narration
  mix" table under the version name.

## Not checked by code
Pronunciation, tone and how natural the clone sounds. The maker listens before uploading and can use the file without
the voice instead.

## AI disclosure
The narration is an AI clone of the maker's own voice (ElevenLabs), reading the on-screen captions. This goes in the
README, the upload texts and the page in both languages once the narrated files exist.

## Rollback
The files without the voice need no new render. In code: `voice.enabled` false and `audio.speech_check.expect` "none",
then render again; caption times before narration are in git history. Characters already spent cannot be refunded;
`char_budget` caps them.

## Takes generated (2026-11-19)
- 14 lines (film-01..10, short-01..04), 19 requests, 837 characters in log/voice.jsonl (char_budget 2500). The
  account had 100958 characters left before the first request and 100590 after the last one (it counted fewer
  characters than the ledger; the ledger counts every character sent).
- Every line has a take with whisper match >= 0.9. Lines that needed more than one take: film-06 (3 takes, 0.857,
  0.857, 1.0), film-08 (3 takes, 0.727, 0.818, 0.909), short-03 (2 takes, 0.818, 1.0). The best take is used.
- Placement: every film line fits its window at tempo 1.0 (longest: film-10, 4.0 s in a 5.3 s window). In the short,
  short-03 (3.84 s) did not fit before short-04 at 10.5 s (it needed tempo 1.325). short-04 moved to 11.5 s, which is
  still inside the same shot (film 42 to 48 s) and closer to where the same line sits in the film (46.5 s); then
  every short line fits at tempo 1.0.
- Caption end times now follow the voice (config/captions.en.json, config/captions.short.en.json); start times are
  unchanged. Both SRT files pass the `srt` limits.
- Landscape preview mix (bed and voice, no picture): voice -16.0 dB, bed under the voice -28.97 dB, gap 12.97 dB,
  bed level change away from the voice 0.0 dB (docs/MEASURED.md "Narration mix").
- Not checked by ear: pronunciation, tone and pacing. Only whisper and the measurements above were used.

## 16:9 render (2026-11-19)
- One pass wrote the narrated 16:9 file and the same picture without the voice. Narrated: -14.0 LUFS, -1.4 dBTP,
  speech match 0.973 (67 words heard), captions 10 of 10; mix gap 12.97 dB, bed outside the voice unchanged (0.0 dB).
  Without the voice: -13.9 LUFS, 0 words heard. Numbers and hashes are in docs/MEASURED.md.
