# PetPulse Quick Start

The [README](../README.md#quick-start) has the short version. This page goes step by step and
ends with troubleshooting.

## 1. Demo (no keys, no accounts)

Local, with Python 3.11 (venv or conda):

```bash
git clone https://github.com/dhyeynala/pet-voice-notes.git
cd pet-voice-notes
python3.11 -m venv .venv && source .venv/bin/activate   # or: conda create -n petpulse python=3.11 && conda activate petpulse
make install                                          # pip install -r requirements/base.txt -r requirements/dev.txt
make run                                              # uvicorn petpulse.app:app --reload ; http://localhost:8000
```

Or with Docker Compose v2.24+: `docker compose up --build` (reset the data with
`docker compose down -v`).

Sign in as Alice or Bob (or create a new demo user). The banner and the Demo / Live badges show
the mode of each feature, and so does `GET /api/health`. "Reset demo data" in the user menu
restores the seed.

## 2. Optional: live AI (OpenAI, billed)

```bash
cp .env.example .env      # once; running it again overwrites your key
```

Set `OPENAI_API_KEY=sk-...` in `.env` on its own line. Don't add a comment after a value:
Docker Compose would read the comment as part of the value. Restart the app. With the default
`LLM_PROVIDER=auto` / `STT_PROVIDER=auto`, both switch to OpenAI with the pinned models
`OPENAI_MODEL` and `STT_OPENAI_MODEL`. To check the setup with at most 6 calls, run
`make smoke-live-local`; see [live-smoke.md](live-smoke.md).

Google Speech-to-Text is opt-in. It needs `STT_PROVIDER=google`, `GOOGLE_APPLICATION_CREDENTIALS`
and the live extras (`pip install -r requirements/live.txt`, or
`INSTALL_LIVE=true docker compose build`).

## 3. Optional: Firebase (Firestore + Firebase sign-in)

1. Set `FIREBASE_CREDENTIALS_JSON` (service-account key) and `FIREBASE_WEB_API_KEY` in `.env`.
2. Install the live extras.
3. Deploy `firestore.rules` and `storage.rules`.

With the default `STORE_BACKEND=auto` / `AUTH_PROVIDER=auto`, the app then uses Firestore and
shows "Continue with Google" / email sign-in instead of the demo picker. There is no client
config file to edit: the browser gets its Firebase config from `GET /api/auth/config`. Full
steps: [firebase.md](firebase.md).

Every setting, with its default, is listed in [`.env.example`](../.env.example).

## Troubleshooting

- **Startup fails with "Invalid PetPulse configuration".** The message lists what is missing,
  for example `LLM_PROVIDER=openai` without a key, or Firebase forced but only half configured.
  Fix the setting, or go back to `auto`.
- **A setting "looks like a comment" warning at startup.** A value in `.env` starts with `#`, so
  a comment ended up after `=`. It is ignored. Move the comment to its own line.
- **Firebase sign-in errors** ("domain not authorised", "sign-in method not enabled"). In the
  Firebase console, add your origin under Authentication > Settings > Authorized domains and
  enable the provider.
- **Port 8000 in use.** Run `uvicorn petpulse.app:app --port 8001` and add the origin to
  `ALLOWED_ORIGINS`.
- **Docker runs old code.** Run `docker compose up --build` (`make smoke-live` always rebuilds).
- **Docker cache issues.** Run `docker compose build --no-cache`.

## Security

Never commit `.env` or any service-account key. Firebase web API keys are public config, but
restrict them to your domains in the Google Cloud console. See [SECURITY.md](../SECURITY.md).

## Next steps

- [README.md](../README.md): overview and architecture.
- [api-contract.md](api-contract.md): the API.
- [live-smoke.md](live-smoke.md): the live smoke test.
- [CONTRIBUTING.md](../CONTRIBUTING.md): development.
