# PetPulse

PetPulse is a pet health log. You record voice or text notes about your pet, and it turns them
into structured, searchable records you can show your vet. It runs fully offline as a demo,
with no keys and no accounts, and switches to real OpenAI models when you add a key.

## What it does

- **Notes by voice or text.** Record in the browser, or pick a bundled sample clip if you have
  no microphone. Each note is transcribed, then classified (medical, daily activity, mixed).
  Observations and red flags (for example blood or repeated vomiting) are extracted with the
  sentences they came from. A note with a red flag gets an urgent "contact your vet" banner.
- **Vet records.** Upload a PDF. It is checked, stored privately and summarized: findings,
  medications with doses, and follow-ups, each with the page it came from.
- **Chat with citations.** Questions are answered only from the pet's own notes, records and
  tracking entries, and every answer cites them. Date and count questions are answered by code. Questions that aren't in the records get "not in records".
  Dosing, diagnosis or off-topic questions are refused with a pointer to a veterinarian.
- **Insights.** Facts (for example average energy and exercise over 7 days) and alerts (an
  urgent note, a low-energy streak) computed by code from notes and tracking data, with a headline.
- **Tracking and charts.** Ten form categories (diet, exercise, medication, grooming, energy
  levels, bowel movements, exit events, weight, sleep, mood) and charts over the last weeks.
- **Several pets and users.** Each pet has owners, and every pet route checks ownership.

## Demo vs live

Every AI provider and backend defaults to `auto`:

| | No configuration (demo) | When configured (live) |
|---|---|---|
| LLM (notes, PDF summaries, chat) | deterministic fake | OpenAI when `OPENAI_API_KEY` is set; model pinned by `OPENAI_MODEL` (`gpt-5.4-mini-2026-03-17`) |
| Speech-to-text | deterministic fake | OpenAI when `OPENAI_API_KEY` is set (`STT_OPENAI_MODEL`, `gpt-4o-mini-transcribe-2025-12-15`); Google only with an explicit `STT_PROVIDER=google` |
| Storage | local JSON file (`DATA_DIR/db.json`) | Firestore when Firebase service-account credentials are set |
| Sign-in | demo login (pick Alice or Bob, or create a user) | Firebase (Google / email) when credentials and `FIREBASE_WEB_API_KEY` are set |

- An explicit value (`LLM_PROVIDER=fake|openai`, `STT_PROVIDER=...`, `STORE_BACKEND=...`,
  `AUTH_PROVIDER=...`) always wins over `auto`.
- An explicit live choice without its key or credentials fails at startup with a message that
  lists what is missing.
- `OPENAI_MODEL` must be a dated snapshot. Undated aliases are rejected at startup.
- The UI shows a banner with the overall mode and a Demo / Live badge on each AI feature.
  `GET /api/health` reports the same per feature.
- Demo AI output is simulated and marked as such.

The demo seed gives Alice two pets (Max and Luna) and Bob his own Max. It includes about 30
days of tracking data, notes (one of them urgent) and a sample vet PDF. "Reset demo data" in
the user menu restores it.

## Quick start

**Local (Python 3.11):**

```bash
git clone https://github.com/dhyeynala/pet-voice-notes.git
cd pet-voice-notes
python3.11 -m venv .venv && source .venv/bin/activate   # or: conda create -n petpulse python=3.11 && conda activate petpulse
make install        # pinned requirements/base.txt + requirements/dev.txt
make run            # uvicorn petpulse.app:app --reload on http://localhost:8000
```

Open http://localhost:8000 and sign in as Alice. API docs are at http://localhost:8000/docs.

**Docker (Compose v2.24+):**

```bash
docker compose up --build        # http://localhost:8000
docker compose down -v           # stop and reset the demo data volume
```

**Adding an OpenAI key (live AI, billed):**

```bash
cp .env.example .env             # once
# edit .env and set the key on its own line:  OPENAI_API_KEY=sk-...
```

Restart `make run` (or `docker compose up`) and the banner switches to live.

> **Warning:** running `cp .env.example .env` again overwrites `.env`, including your key.
> Edit the existing file instead.

Keep comments on their own lines in `.env`. Docker Compose reads `KEY=value # note` as part of
the value. Every setting and its default is listed in [.env.example](.env.example). For
Firebase, see [docs/firebase.md](docs/firebase.md). More setup notes and troubleshooting are in
[docs/quick-start.md](docs/quick-start.md).

## Live smoke test

One command checks each live feature once (transcription, note classification, PDF summary,
chat). It runs through the app's own services on a temporary in-memory store, so your data is
never touched.

```bash
make smoke-live-dry     # show providers, models and the cap; no calls
make smoke-live-local   # without Docker: local Python environment, reads .env directly
make smoke-live         # in the app image (rebuilds it; reads .env through Compose)
```

- Every call counts against `LIVE_CALL_CAP` (default 6). Once the cap is reached, the remaining
  checks are skipped and never called.
- A full run uses about 4 calls: 1 transcription and 3 LLM calls, plus at most one repair retry
  if a reply fails validation.
- Keys are never printed. A JSON report goes to `reports/`.
- Details: [docs/live-smoke.md](docs/live-smoke.md).

Optional live model eval (note extraction against frozen gold labels):

```bash
python -m evals.run_eval                                    # fake provider: pipeline test, free
python -m evals.run_eval --provider openai --i-accept-cost   # live model, billed
```

The live eval makes one call per case (34 cases) plus at most one repair each, so up to 68
billed calls. It refuses to run without `--i-accept-cost`.

## Repository layout

```
petpulse/                 the backend (FastAPI), run as uvicorn petpulse.app:app
  app.py                  app factory: middleware, startup seed, router registration
  core/                   settings, auth (tokens, ownership), errors, logging, deps, firebase, time
  routers/                HTTP routes: health, demo, pets, records, analytics, notes,
                          assistant (chat), insights, voice
  services/               notes, chat, retrieval, insights, charts, voice, PDF text + summaries
  llm/                    LLM client, schemas, versioned prompts, fake rules
  providers/              LLM and speech-to-text providers (fake, OpenAI, Google)
  store/                  storage: JSON file, in-memory, Firestore; blob stores
  schemas/                request/response models
  seed/                   demo data and bundled audio/PDF samples
public/                   the UI (static HTML/CSS/JS, vendored Chart.js, Font Awesome, Firebase SDK)
tests/
  unit/                   modules and services, no HTTP
  integration/            the app over HTTP, scripts and entry points
  js/                     node:test tests for public/js
evals/                    note-extraction cases, gold labels, scorer
scripts/                  smoke_live.py (live smoke test), make_samples.py (regenerate samples)
docs/                     quick-start, api-contract, live-smoke, firebase, images/
requirements/             base.txt, dev.txt, live.txt (pinned locks; *.in are the sources)
Dockerfile, docker-compose.yml, Makefile, pyproject.toml, .env.example
firestore.rules, storage.rules, firebase.json    Firebase rules (optional Firebase mode)
```

Docs:
- [docs/quick-start.md](docs/quick-start.md): setup and troubleshooting.
- [docs/api-contract.md](docs/api-contract.md): every route, its body and its errors.
- [docs/live-smoke.md](docs/live-smoke.md): the live smoke checklist.
- [docs/firebase.md](docs/firebase.md): optional Firebase mode.
- [CONTRIBUTING.md](CONTRIBUTING.md): development workflow.

## Testing and CI

```bash
make test    # pytest (tests/unit, tests/integration) + node --test tests/js/*.test.mjs
make lint    # black --check, flake8, mypy (strict, petpulse/), bandit, detect-secrets
make smoke-fake   # the smoke script against the fakes (what CI runs)
```

The JS tests need Node 20 and no `npm install`. Tests never call a live API: providers are
fakes, and the OpenAI adapters are tested against mocked or local stand-in servers.

CI runs on every push and PR, with no secrets anywhere:
- **lint:** flake8, black, mypy, a JS syntax check, and the JS tests.
- **test:** pytest with a 60% coverage floor, plus the smoke script (`--dry-run` and
  `--allow-fake`). It fails if a provider key is present.
- **security:** bandit on `petpulse scripts evals`, and detect-secrets against `.secrets.baseline`.
- **docker:** builds the image, then checks:
  - the image starts with no env in demo mode (`/api/health` reports demo/fake);
  - the demo login sees the seeded pets and an anonymous request is a 401;
  - the healthcheck turns healthy and the smoke script passes inside the image;
  - `.env.example` copied to `.env` parses cleanly through `docker compose run`.

## Security notes

- **No secrets in the repo.** `.env` and key files are git-ignored, detect-secrets gates every
  PR, and keys are never logged or printed (the smoke script shows only the last 4 characters).
- **Owner-only access.** Every `/api` route except health, auth config and the demo login needs
  a bearer token. The caller always comes from the token. A pet comes only from the
  `/api/pets/{pet_id}` path, and a pet the caller doesn't own is a 404, so ids can't be probed.
  Demo tokens are HMAC-signed (`AUTH_SECRET`). Firebase ID tokens are verified with the Admin SDK.
- **Uploads.** Size caps, a `%PDF-`/audio sniff, and server-generated storage keys. Files are
  served only through owner-checked routes.
- **Errors.** One JSON error shape with a request id. 500s never include exception text.
- **CORS.** An explicit allow-list (`ALLOWED_ORIGINS`), never `*`, no credentials.
- **Firebase rules.** `firestore.rules` and `storage.rules` allow a signed-in user only their
  own user doc and the pets they own. Clients can never change a pet's owners and never write
  to Storage.
- See [SECURITY.md](SECURITY.md) for handling keys.

## Known limits

- **Chat search is keyword-based.** If no note or record contains the question's words, the
  answer is "not in records" without asking the model. For example, "What medication is he on?"
  finds nothing when the notes only say "started Apoquel".
- **Old data isn't migrated.** Notes the pre-contract app wrote to the `textinput` and
  `voice-notes` collections are ignored. Only `pets/{id}/notes` is read.
- **Firebase mode needs a service-account key** (`FIREBASE_CREDENTIALS_JSON`, or
  `GOOGLE_APPLICATION_CREDENTIALS` plus `FIREBASE_PROJECT_ID`) and the live extras
  (`requirements/live.txt`).
- **The demo login is not real authentication.** Anyone who can reach the server can sign in as
  any demo user. Use Firebase sign-in for anything beyond a local demo.
- **Voice clips are capped** at 60 s and 5 MiB. Google STT cannot decode Safari's `audio/mp4`
  (OpenAI can).

## License

MIT, see [LICENSE](LICENSE).
