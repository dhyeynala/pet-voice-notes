# Optional Firebase mode

PetPulse runs with zero secrets by default (local JSON store, demo login). Firebase is an
**optional** backend for the same app, selected the same way as the AI providers:

| Setting | Values | `auto` means |
|---|---|---|
| `STORE_BACKEND` | `auto` \| `json` \| `firestore` | Firestore when service-account credentials are configured, else the local store (`STORE=json\|memory`) |
| `AUTH_PROVIDER` | `auto` \| `demo` \| `firebase` | Firebase sign-in when service-account credentials **and** `FIREBASE_WEB_API_KEY` are configured, else the demo login |

An explicit `firestore` / `firebase` without what it needs fails at startup with a clear message;
so do credentials that are present but broken (bad JSON, not a service-account key, project
mismatch), and Firebase without the `firebase-admin` package. Nothing falls back silently.
`GET /api/health` reports what was picked: `store` (`json|memory|firestore`), `auth`
(`demo|firebase`) and `blobs` (`local|firebase`).

`firebase-admin` is **not** in the base image. It is pinned in `requirements-live.txt` and
imported lazily, only in Firebase mode:

```bash
pip install -r requirements.txt -r requirements-live.txt     # local
INSTALL_LIVE=true docker compose build                        # Docker
```

## Settings

| Variable | Purpose |
|---|---|
| `FIREBASE_PROJECT_ID` | Project id. Optional when `FIREBASE_CREDENTIALS_JSON` is set (taken from the key); must match it if both are set. |
| `FIREBASE_CREDENTIALS_JSON` | Service-account key as inline JSON (e.g. from a secret manager). Wins over the file below. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to a service-account key file. Counts as a Firebase credential **only** together with `FIREBASE_PROJECT_ID` and only if the key's `project_id` matches, so a Google STT key never switches the app to Firebase. |
| `FIREBASE_STORAGE_BUCKET` | e.g. `my-project.firebasestorage.app`. With the Firestore store, record PDFs go to this bucket; empty = they stay in `DATA_DIR/blobs` (local disk). |
| `FIREBASE_WEB_API_KEY` | Browser SDK `apiKey` (public config, not a secret). Needed for Firebase sign-in. |
| `FIREBASE_AUTH_DOMAIN` | Default `<project>.firebaseapp.com`. |

Never commit a key file or a `.env`; `.gitignore` / `.dockerignore` exclude the usual names.

## Turning it on

1. Create a Firebase project; enable **Firestore** (Native mode), **Authentication** (e.g. the
   Google and/or Email/Password providers) and, if you want PDFs in the cloud, **Storage**.
2. Add a Web app in the console to get its `apiKey`. Add your app's origin to
   Authentication -> Settings -> Authorized domains.
3. Create a service-account key (Project settings -> Service accounts -> Generate new private key).
4. Deploy the rules: `firebase deploy --only firestore:rules,storage` (uses `firebase.json`).
5. Configure `.env`:

   ```bash
   FIREBASE_CREDENTIALS_JSON='{"type":"service_account","project_id":"my-project",...}'
   FIREBASE_WEB_API_KEY=AIza...
   FIREBASE_STORAGE_BUCKET=my-project.firebasestorage.app   # optional
   ALLOWED_ORIGINS=https://my-app.example
   ```

   With `auto` this gives Firestore + Firebase sign-in. Mix and match explicitly if needed, e.g.
   `AUTH_PROVIDER=demo` (demo login on Firestore) or `STORE_BACKEND=json` (Firebase sign-in on
   the local store). Every Firebase mode needs the service account: the Admin SDK uses it even
   to verify ID tokens (without one it probes Application Default Credentials and every request
   fails), so it is required up front rather than failing per request.
6. Start the app and check `GET /api/health` (`"store": "firestore", "auth": "firebase"`).

## What changes in Firebase mode

**Sign-in.** `current_user` accepts only Firebase ID tokens
(`firebase_admin.auth.verify_id_token`: signature, expiry, issuer, audience = this project).
The token's `uid` becomes the user id used everywhere (`pets/{id}.owners`), so ownership checks
are unchanged: another user's pet is 404. A uid is never taken from the request body or path.
Demo tokens are rejected; any bad, expired or foreign-project token is 401; if Google's signing
certificates can't be fetched the API answers 503 (`code: "auth_unavailable"`) instead of 401
so the UI does not log the user out. On first sign-in `users/{uid}` is created from the token's
`name`/`email` (`demo: false`). Uids must match `[A-Za-z0-9_-]{1,64}` (Firebase's own 28-char
uids always do; exotic custom-token uids are refused with 401). Revocation is not checked per
request (`check_revoked=False`; ID tokens expire after one hour).

**Demo endpoints.** With Firebase sign-in, `/api/demo/users`, `/api/demo/login` and
`/api/demo/reset` return 404 with `code: "demo_login_disabled"`. With the Firestore store,
`POST /api/demo/reset` returns 409 (`code: "reset_disabled"`): a signed-in user can never wipe
a real project. The startup seed (`SEED_ON_START`) is skipped under Firebase sign-in (its
owners are demo logins nobody could use); with demo login on Firestore it seeds an empty
database once.

**Storage.** `FirestoreStore` implements the same `Store` interface as `JsonFileStore`
(`petpulse/store/firestore.py`), same paths: `users/{uid}`, `pets/{id}` with sub-collections
(`notes`, `analytics`, `records`, `voice-notes`, `textinput`), `llm_calls`, `meta/seed`.
`set(merge=True)` stays a shallow merge (sent as an explicit field list), `ArrayUnion` maps to
the Firestore transform, `add` uses uuid4 hex ids. All queries are single-field, so no composite
indexes are needed. `FirebaseBlobStore` keeps objects private; PDFs are served only through the
owner-checked `GET /api/pets/{pet_id}/records/{record_id}/file`.

## Security rules

The backend uses the Admin SDK, which **bypasses** security rules, and enforces ownership in
code. `firestore.rules` and `storage.rules` cover direct client access: a signed-in user can
read/write only their own `users/{uid}` and the pets whose `owners` contain their uid (plus
those pets' sub-collections); new pets must be owned by their creator alone, owners cannot change
`owners`; everything else (`llm_calls`, `meta`, ...) is server-only. Storage: owners may read
their pets' record files; clients never write.

## Frontend

The login page (`public/index.html`, `public/js/login.js`) reads `auth` from `GET /api/health`
and shows the matching `<section data-login-method>`: the demo picker, or in Firebase mode
"Continue with Google" plus email/password (sign in or create an account). The browser config
comes from `GET /api/auth/config` (public):

```json
{"provider": "demo", "mode": "demo", "firebase": null}
{"provider": "firebase", "mode": "firebase",
 "firebase": {"apiKey": "...", "authDomain": "my-project.firebaseapp.com", "projectId": "my-project"}}
```

- The Firebase JS SDK (app + auth, 12.19.0) is vendored under `public/vendor/firebase-12.19.0/`
  (version, source, license and sha256 in `public/vendor/README.md`) and loaded with `import()`
  only in Firebase mode, so demo mode never downloads it. Sign-in itself talks to Google
  (Identity Toolkit, the `authDomain` pop-up): that is inherent to Firebase and opt-in.
- After sign-in the Firebase ID token is the bearer token (stored per tab in `sessionStorage`,
  like the demo token, with Firebase's per-tab persistence). `GET /api/me` completes the login
  and creates the user record.
- Tokens last an hour: the app stores each rotated token (`onIdTokenChanged`), and on a 401 a
  Firebase session asks the SDK for a fresh token and retries once before going back to the
  login page (concurrent 401s share one refresh). A 503 `auth_unavailable` does not sign out.
- Firebase sessions get only "Log out" in the user menu (switch user / reset demo data are
  demo-only); log out also signs out of Firebase. The banner says data and sign-in use Firebase.

### Trying it locally with the emulators

No real project needed: with the Firebase CLI, `firebase emulators:start --only firestore,auth
--project demo-petpulse`, then start the app with `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080`,
`FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099`, `FIREBASE_WEB_API_KEY=any-value` and a
service-account key whose `project_id` is `demo-petpulse` (any throwaway RSA key works; the
emulators do not check it). `/api/auth/config` then adds `authEmulatorUrl` and the browser signs
in against the Auth emulator. `FIREBASE_AUTH_EMULATOR_HOST` makes the Admin SDK accept unsigned
tokens, so startup refuses it unless the project id starts with `demo-`.

## Limitations

- Application Default Credentials (e.g. Cloud Run's service identity) are not used; pass a key
  via `FIREBASE_CREDENTIALS_JSON` or the key file.
- Writes go straight to Firestore (no batching); Firestore's own limits apply (1 MiB documents,
  at most 30 values for `in`, arrays may not directly contain arrays).
- CI never talks to Firebase: the store, blob store and token checks are tested against
  in-process fakes of the SDK (`tests/fake_firebase.py`).
