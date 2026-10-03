# PetPulse Quick Start

PetPulse runs as a **demo with zero secrets**: deterministic fake AI, a local JSON store and a
demo login. OpenAI and Firebase are optional add-ons, each switched on just by configuring it.

## 1. Demo (no keys, no accounts)

Docker Compose v2.24+:

```bash
git clone https://github.com/dhyeynala/pet-voice-notes.git
cd pet-voice-notes
docker compose up --build        # http://localhost:8000
docker compose down -v           # reset demo data
```

Without Docker (Python 3.11):

```bash
pip install -r requirements/base.txt                # or: make install (adds dev tools)
uvicorn petpulse.app:app --reload                   # or: make run ; http://localhost:8000, API docs at /docs
```

Log in as Alice or Bob (or create a new demo user). `GET /api/health` shows the mode of every
feature.

## 2. Optional: live AI (OpenAI)

```bash
cp .env.example .env
# set OPENAI_API_KEY=... (calls are billed); providers on `auto` switch to OpenAI
```

Google Speech-to-Text is opt-in: `STT_PROVIDER=google` plus `GOOGLE_APPLICATION_CREDENTIALS`
and the live extras (`pip install -r requirements/live.txt`, or
`INSTALL_LIVE=true docker compose build`).

## 3. Optional: Firebase (Firestore + Firebase sign-in)

Set `FIREBASE_CREDENTIALS_JSON` (service-account key) and `FIREBASE_WEB_API_KEY` in `.env`,
install the live extras, and deploy `firestore.rules` / `storage.rules`. With the default
`STORE_BACKEND=auto` / `AUTH_PROVIDER=auto` the app then uses Firestore and shows a
"Continue with Google" / email sign-in instead of the demo picker. There is no client config
file to edit: the browser gets its Firebase config from `GET /api/auth/config`. Full steps:
[firebase.md](firebase.md).

Every setting, with its default, is listed in [`.env.example`](../.env.example).

## Troubleshooting

- **Startup fails with "Invalid PetPulse configuration"**: the message lists what is missing,
  e.g. `LLM_PROVIDER=openai` without a key, or Firebase forced/half-configured. Fix the setting
  or go back to `auto`.
- **Firebase sign-in errors** ("domain not authorised", "sign-in method not enabled"): add your
  origin under Authentication > Settings > Authorized domains and enable the provider in the
  Firebase console.
- **Port 8000 in use**: `uvicorn petpulse.app:app --port 8001` (and add the origin to
  `ALLOWED_ORIGINS`).
- **Docker cache issues**: `docker compose build --no-cache`.

## Security

Never commit `.env` or any service-account key. Firebase web API keys are public config, but
restrict them to your domains in the Google Cloud console. See [SECURITY.md](../SECURITY.md).

## Next steps

[README.md](../README.md) (architecture), [api-contract.md](api-contract.md) (API),
[live-smoke.md](live-smoke.md) (live smoke test), [CONTRIBUTING.md](../CONTRIBUTING.md) (development).
