# 0004: Music, mix levels and the speech check

Date: 2026-11-16. Status: accepted.

## Music
One cue for the whole film from `config/music.json`: D major, 84 bpm, D Bm G A, five sections that tile the 60 s
(density and register per section) and a three note kalimba motif at 44 s when the coin is handed over. Layers: detuned
sine pad, Karplus-Strong plucked root in sections with density at least 0.5, seeded kalimba notes on chord tones.
The random generator is drawn on every step, so changing one section never moves the notes of another. Same config,
same WAV bytes (unit test).

## Mix
Ambience is the clips' own audio inside each edit window, placed at its film seconds with 0.25 s fades at cuts; the end
card has music only. Each stem is set to an RMS level (music -18, ambience -24 dBFS) before summing. The toll bridge
window has one splash 35 dB above its average, so plain levelling would have pushed it far over full scale; a block
limiter (10 ms blocks, gain interpolated between block centres) holds ambience peaks under -12 dBFS and the sum under
-1 dBFS without touching quiet passages. Loudness to -14 LUFS happens once, in the edit.

## Speech check runs voice activity detection first
faster-whisper `small.en` without voice activity detection returned stock video outro phrases on audio that has no
voice: "Music" and "Thanks for watching!" on the synthesised music, "Let's see what's going on." and "Don't forget to
like and subscribe to our channel!" on the mix (no-speech probability 0.36 to 0.40, average log probability -1.4 to
-1.7; the text changes from run to run). With the Silero voice activity detection filter of faster-whisper, both files
return no segments. The check now runs with `audio.speech_check.vad_filter: true`. The rule is unchanged: more than 0
words fails.

Amended 2026-11-19 by decision 0012: a narrated version must instead be heard saying the script (`speech_match` at
least `audio.speech_check.match_min`); the copy without the voice keeps the 0 word rule.

## Rollback
Set `vad_filter` to false to see the raw model output. Mix levels and limiter ceiling live in `config/music.json` `mix`.
