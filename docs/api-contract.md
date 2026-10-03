# Demo build: shared API contract (all tracks code against this)

All JSON. Errors: non-2xx with {"detail": str, "request_id": str}. No more {"error": ...} with 200.
Auth: every /api route except /api/health, /api/demo/users, /api/demo/login requires
`Authorization: Bearer <token>` (401 otherwise). Token is HMAC-signed by the backend (secret from
settings, generated at startup if unset). Helpers in `petpulse/core/auth.py` (Track A):
`current_user() -> User(uid, name)` and `require_pet_access(pet_id) -> Pet` (404 unless user in pet.owners).

## Demo + pets (Track A)
- GET  /api/demo/users            -> [{"uid":"alice","name":"Alice"},{"uid":"bob","name":"Bob"}]
- POST /api/demo/login {"uid"}    -> {"token","user":{"uid","name"}}
- POST /api/demo/reset            -> reseed demo data (auth required)
- GET  /api/me                    -> {"uid","name"}
- GET  /api/me/pets               -> [Pet]
- POST /api/pets  PetCreate       -> Pet          (id = uuid4, owners=[uid])
- GET  /api/pets/{pet_id}         -> Pet
Pet = {id, name, animal_type, breed, age, weight, gender, owners, created_at}
Seed: Alice owns "Max" (dog) and "Luna" (cat); Bob owns his own "Max". ~30 days of entries, one urgent note.
The few pre-contract routes still mounted live in `petpulse/routers/legacy.py` and are auth+ownership protected (see Legacy routes below).

## Records / uploads + analytics (Track B)
- POST /api/pets/{pet_id}/records  multipart file=PDF -> Record  (size cap, %PDF- check, server filename)
- GET  /api/pets/{pet_id}/records                    -> [Record]
- GET  /api/pets/{pet_id}/records/{record_id}/file   -> PDF bytes (owner only)
Record = {id, pet_id, filename, pages, summary|null, status, created_at}
- POST /api/pets/{pet_id}/analytics/{category} body=typed schema (extra=forbid) -> Entry
- GET  /api/pets/{pet_id}/analytics?category=&days= -> [Entry]

## Notes, chat, insights (Track C)
- POST /api/pets/{pet_id}/notes {"text","tz"} -> Note
- GET  /api/pets/{pet_id}/notes?limit=        -> [Note]
Note = {id, pet_id, source: "text"|"voice"|"pdf", text, summary|null, kind, urgent, needs_review,
        red_flags:[{flag,status,sentences}], observations:[...], status, created_at, mode:"demo"|"live"}
Service (used by Track D): `petpulse.services.notes.process_note(pet_id, uid, text, source, tz) -> Note`
- POST /api/pets/{pet_id}/chat {"message","tz"} -> {answer, status:"answered"|"not_in_records"|"out_of_scope",
        citations:[{id,date,source,snippet}], chart: null|{type,title,data}, mode}
- GET  /api/pets/{pet_id}/insights?tz=        -> {facts, alerts, headline, mode}

## Voice (Track D)
- GET  /api/voice/samples                       -> [{"id","label"}]
- POST /api/pets/{pet_id}/voice-notes multipart audio=<blob>, tz  (or form field sample_id)
       -> {"transcription":{"status","text","confidence"},"note": Note}
       422 no_speech (nothing stored), 502 stt error (nothing stored), 415 unsupported type

As implemented by Track D: success is **201**. Also **413** (over `VOICE_MAX_BYTES`, 5 MiB, or
`VOICE_MAX_SECONDS`, 60 s, where the container header gives a duration) and **400** (both or
neither of `audio`/`sample_id`, unknown `sample_id`, unknown `tz`). Accepted containers:
webm, ogg, mp4, wav (sniffed from the bytes; `audio/webm;codecs=opus` etc. are fine). On `ok` the
transcript goes to `await process_note(pet_id, uid, text, "voice", tz, store=, llm=)`, so the note
is stored at `pets/{pet_id}/notes/{id}` like a typed note (same `urgent`/`red_flags` rules; an LLM
failure stores an `unprocessed` note, still 201); its `ValueError` (e.g. transcript over 5000
characters) is a **400**. Samples:
`walk_and_dinner`, `vomiting_blood` (urgent), `heartworm_pill`, `silence` (-> 422).

## Health (exists)
- GET /api/health -> {"mode":"demo"|"live"|"mixed", features:{notes,chat,pdf_summary,insights,voice}, store, llm, stt}

---

## As implemented by Track A (auth/data)

Everything above holds. These are the details and the small additive extensions, so other
tracks and the frontend don't have to read the code.

### Login flow (frontend)
1. `GET /api/demo/users` (public) -> `[{"uid":"alice","name":"Alice"},{"uid":"bob","name":"Bob"}, ...]`.
   Users created by name (below) are listed after the two seeded ones.
2. `POST /api/demo/login` with `{"uid":"alice"}` -> `{"token": "...", "user": {"uid","name"}}`.
   *Extension:* `{"name": "Sam"}` instead of `uid` creates a new demo user (uid `sam-<8 hex>`)
   with no pets. Send exactly one of `uid` / `name` (422 otherwise); unknown `uid` -> 404.
3. Keep the token in `sessionStorage` (per tab, so Alice and Bob can be open side by side) and
   send `Authorization: Bearer <token>` on every `/api` call.
4. Any 401 means "log in again": drop the token and go back to the user picker. Tokens expire
   after `AUTH_TOKEN_TTL_MINUTES` (default 720), and when `AUTH_SECRET` is unset the secret is
   random per process, so a server restart also invalidates them.
5. `GET /api/me` -> `{"uid","name"}`; `GET /api/me/pets` -> `[Pet]` (oldest first).

All `/api/demo/*` routes return 404 when `DEMO_MODE=false`.

### Statuses and error body
- Every non-2xx body is `{"detail": str, "request_id": str}`, plus optionally `"code"` (short
  machine-readable reason, e.g. `"no_speech"`) and, for 422, `"errors": [{"loc","msg","type"}]`
  (submitted values are never echoed). The id is also in the `X-Request-ID` response header
  (exposed to CORS) and in the server log next to the traceback. 500s are always
  `{"detail": "internal server error", "request_id"}`.
- 401 (with `WWW-Authenticate: Bearer`): no token / wrong scheme (`"not authenticated"`) or a
  bad/expired token (`"invalid or expired token"`).
- 404 `"pet not found"`: the pet does not exist **or** the caller is not in `owners` (same
  answer, so ids can't be probed).
- 403: only on legacy routes that carry a uid (`/api/user-pets/{user_id}`,
  `POST /api/pets/{user_id}`, `uid` in a body) when it is not the caller.
- `POST /api/pets` returns **201** with the Pet. `PetCreate` = `name` (1-60 chars),
  `animal_type` (`dog|cat|bird|rabbit|hamster|guinea-pig|fish|reptile|other`), optional `breed`
  (<=80), `age` (0-40), `weight` (0-500), `gender` (`male|female|male-neutered|female-spayed`,
  `""` = none); `extra="forbid"`.
- Raise errors with `petpulse.core.errors` (`NotFoundError`, `UnprocessableError(detail, code=...)`,
  `BadGatewayError`, `UnsupportedMediaTypeError`, `PayloadTooLargeError`, ...). They are
  `HTTPException`s; plain `HTTPException` also gets the same body.

### Using the auth helpers (backend tracks)
```python
from petpulse.core.auth import Pet, User, current_user, require_pet_access

@router.get("/api/pets/{pet_id}/notes")
def list_notes(pet: Pet = Depends(require_pet_access)): ...        # pet.id, pet.owners, ...

@router.get("/api/voice/samples")
def samples(user: User = Depends(current_user)): ...
```
`tests/integration/test_auth.py` walks the OpenAPI schema: every new `/api` route automatically gets the
401 (no/bad token) check, and every route with `{pet_id}` the 404-for-another-user check. New
routes must therefore use one of the two dependencies (or be added to the public list there,
which needs a reason).

Test fixtures: `client` is signed in as `alice` (the default owner for `make_pet()`),
`anon_client` has no credentials, `client_as("bob")` signs in as anyone.

### Data layout (Store)
- `users/{uid}`: `{name, email, demo, created_at}`.
- `pets/{id}`: `{name, animal_type, breed, age, weight, gender, owners, created_by, created_at,
  schema_version: 2}`; `id` is a uuid4. No `pages`, no `default-page`. Helpers in
  `petpulse/services/pets.py` (`create_pet`, `get_pet`, `list_pets`, `is_owner`, `to_pet`).
- Per-pet data stays in sub-collections: `analytics`, `notes`, `records`.
- `Pet.created_at` / note `created_at`: ISO-8601 UTC with offset (`...+00:00`). Analytics
  `timestamp`s stay in the legacy naive-UTC format the old dashboard parses.

### Seed
- Loaded at startup when `SEED_ON_START=true` (default) and the store has no users and no
  pets; never touches a non-empty store. `POST /api/demo/reset` (any signed-in user) wipes the
  whole store and reseeds; response
  `{"status":"reset","seed":{"version","users","pets","analytics","notes","records"}}`.
  Tokens stay valid across a reset. A reset first deletes the blob of every stored record
  (uploads included), then wipes the store.
- One sample vet-record PDF for Alice's Max (`maple-street-vet-visit.pdf`, a one-page synthetic
  note made with PyMuPDF, dated day -12 like the seeded vet-visit exit event), written through
  `petpulse.routers.records.create_record`, so it is stored and summarized like an upload. It is
  only seeded while the LLM resolves to the fake (no billed call at startup); with a live key
  `seed.records` is 0.
- Fixed uuid4 pet ids, so a reset keeps ids stable: Alice's Max
  `638452ec-3d34-4f2c-8d6b-5765533e2287`, Alice's Luna `72949cb3-b5b3-4ac1-aa47-8a9e4dc8c268`,
  Bob's Max `ade67093-1441-48e3-802f-5dcd551135b0` (`petpulse.seed.demo_data`).
- Alice's Max: ~30 days of entries in all ten form categories (`diet, exercise, medication,
  grooming, energy_levels, bowel_movements, exit_events, weight, sleep, mood`, field names as in
  the UI forms) with an energy dip over the last 7 days; 8 notes, the newest (day -1) urgent:
  "Max vomited twice this morning and there was some blood..." (`red_flags` blood +
  repeated_vomiting present); the oldest (day -40) mentions him being tired. Luna and Bob's Max
  have fewer entries and 2 / 1 notes.
- Seeded notes are written in the `Note` shape (without `id`, plus `pet_id`, `uid`, `tz`) to
  `pets/{id}/notes`, the only place notes live (typed, voice and PDF alike).

### Legacy routes
Four pre-contract routes are still mounted, in `petpulse/routers/legacy.py`, all protected:
`POST /api/upload_pdf` and `POST /api/markdown` need `pet` owned by the caller and `uid` (if
sent) equal to the caller; `GET /api/markdown?pet=` checks the pet; `GET /api/user-pets/{user_id}`
and `POST /api/pets/{user_id}` need `user_id` to be the caller (403 otherwise). Each one except
markdown has a contract replacement (`POST /api/pets/{pet_id}/records`, `GET /api/me/pets`,
`POST /api/pets`), and the UI uses only the contract routes. Markdown is stored on the pet only.
Errors use the shared envelope.

Removed: `/api/test`, `/api/pages/invite`, `GET|POST /api/pages/{page_id}`, the
server-microphone routes `/api/start`, `/api/start_recording`, `/api/stop_recording`,
`/api/recording_status` (Track D, review C5), and (Track F) `POST /api/pets/{pet_id}/textinput`,
`POST /api/pets/{pet_id}/knowledge_search`, `GET /api/pets/{pet_id}/assistant_summary`,
`GET /api/pets/{pet_id}/health_insights`, `POST /api/pets/{pet_id}/daily_routine`,
`POST /api/pets/{pet_id}/preload`, `POST /api/pets/{pet_id}/cache/clear`,
`GET /api/pets/{pet_id}/cache/status`, `GET /api/pets/{pet_id}/analytics/summary`,
`GET /api/pets/{pet_id}/visualizations`, and the `{"query"}` body of `POST /api/pets/{pet_id}/chat`
(the contract `{"message","tz"}` handler owns that path; a `query` body is a 422). The analytics
routes are registered once, by `petpulse/routers/analytics.py`. They answer 404 (or 405 where
the path still exists for another method); `tests/integration/test_auth.py` asserts that.

Every router imports `require_pet_access` from `petpulse.core.auth`; the route-inventory test
in `tests/integration/test_auth.py` reads the OpenAPI schema, so every new
`/api/pets/{pet_id}/...` route is checked for 401 (no token) and 404 (another user's pet)
automatically.

---

## Optional Firebase mode (Track G)

Default behaviour is unchanged (demo login, local store). Details and setup: `docs/firebase.md`.

- `GET /api/auth/config` (public) -> which sign-in to show:
  `{"provider":"demo","mode":"demo","firebase":null}` or
  `{"provider":"firebase","mode":"firebase","firebase":{"apiKey","authDomain","projectId"}}`
  (plus `authEmulatorUrl` only for `demo-*` emulator projects). Used by `public/js/firebase.js`.
- `GET /api/health` gains `"auth": "demo"|"firebase"` and `"blobs": "local"|"firebase"`;
  `"store"` now reports the resolved store (`"json"|"memory"|"firestore"`).
- With `AUTH_PROVIDER` resolving to `firebase`: `Authorization: Bearer <Firebase ID token>` replaces
  the demo token on every `/api` call (same header, same 401/404 rules; demo tokens are rejected).
  The verified token's uid is the user id (`owners`). 503 `code: "auth_unavailable"` = token could
  not be checked right now (do not sign out). `/api/demo/*` -> 404 `code: "demo_login_disabled"`.
- With the Firestore store: `POST /api/demo/reset` -> 409 `code: "reset_disabled"`.
