# Live smoke test checklist

The demo runs on deterministic fakes with no keys. This checklist proves the **real** providers
work once you add a key: one command calls each AI feature once, through the same services the
app uses, on a temporary in-memory store (your demo data is never touched).

| # | Check | Input | Pass criteria |
|---|---|---|---|
| 1 | `voice_transcription` | `petpulse/samples/audio/smoke_note.webm` (5 s synthetic TTS: "Max vomited twice this morning and there was some blood.") | status `ok`; transcript contains at least 2 of {vomit, blood, twice} |
| 2 | `note_classification` | the transcript from #1 (or the fixed sentence) via `petpulse.services.notes.process_note` | `kind` MEDICAL or MIXED; `blood` or `repeated_vomiting` flag present; `urgent=True` |
| 3 | `pdf_summary` | `petpulse/samples/pdfs/smoke_record.pdf` (1 page, "Apoquel 16 mg", "recheck in 2 weeks") via `POST /api/pets/{id}/records` | a summary mentioning Apoquel; every cited page is 1 |
| 4 | `chat_answer` | 5 fixed notes (seeded with the fake, no live calls) + "What medication is Max on?" via `POST /api/pets/{id}/chat` | `status=answered`; cites the Apoquel note; all citations are in the given set |

All four checks run on `demo/integration`; a check reports `SKIPPED (not available)` only if its
route is not mounted.

## Steps

1. `cp .env.example .env` and set `OPENAI_API_KEY=...`. With `LLM_PROVIDER=auto` and
   `STT_PROVIDER=auto` (the defaults) the key switches both to OpenAI. Leave `LIVE_CALL_CAP=6`.
   The STT model is pinned by `STT_OPENAI_MODEL` (default `gpt-4o-mini-transcribe-2025-12-15`;
   `whisper-1` also works).
2. Rebuild the image so it has the current code: `docker compose build`
   (`INSTALL_LIVE=true docker compose build` only if you want Google STT).
3. Dry run, no calls: `make smoke-live-dry`. Check the printed providers and models, the cap,
   and that the key shows only as `…abcd` (last 4 characters).
4. Run it: `make smoke-live`. Expect 4 provider calls (at most `LIVE_CALL_CAP`), a few seconds,
   and a cost of a few cents at most; check the current prices on the provider's pricing page.
   Each line shows `PASS`/`FAIL`/`SKIPPED`, the provider and model, calls and time. The JSON
   report lands in `reports/smoke-live-<timestamp>.json`.
   - Exit code 0: everything passed or was skipped. 1: at least one FAIL. 2: configuration
     error (for example `LLM_PROVIDER=openai` without a key, or no live provider at all).
   - Without Docker: `make smoke-live-local` (same script, local Python environment).
5. Optional manual check: `docker compose up`, sign in, record one real voice note (or pick a
   sample recording) and ask one chat question. `/api/health` should report the features as
   `live`.
6. Back to demo mode: empty `OPENAI_API_KEY` (or set `LLM_PROVIDER=fake` and
   `STT_PROVIDER=fake`), or delete `.env`. Rotate or delete the key if it was a throwaway.

## Google Speech-to-Text (optional)

- `STT_PROVIDER=google` is explicit only (`auto` never picks it). It needs
  `INSTALL_LIVE=true docker compose build` and a service-account JSON:
  `GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json` in `.env`, mounted with
  `make smoke-live DOCKER_RUN_ARGS="-v $HOME/sa.json:/secrets/sa.json:ro"`.
- Google v1 accepts WebM/Opus and Ogg/Opus (Chrome, Firefox) and 16-bit PCM WAV. Safari records
  `audio/mp4`, which v1 cannot decode: the app answers 415 for it with Google (OpenAI accepts it).
- Clips are capped at `VOICE_MAX_SECONDS` (60 s), within synchronous recognition's limit.

## Safety

- Hard cap: every provider call goes through a budget of `LIVE_CALL_CAP` calls; when it runs
  out the remaining checks are `SKIPPED (cap)` and never called. LLM calls are clamped to
  `--max-tokens` (600).
- Keys are never printed or written to the report (last 4 characters only).
- CI runs this script with `--allow-fake` and no keys; it never makes a live call.
