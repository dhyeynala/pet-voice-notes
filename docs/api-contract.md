# Demo build: shared API contract (all tracks code against this)

All JSON. Errors: non-2xx with {"detail": str, "request_id": str}. No more {"error": ...} with 200.
Auth: every /api route except /api/health, /api/demo/users, /api/demo/login requires
`Authorization: Bearer <token>` (401 otherwise). Token is HMAC-signed by the backend (secret from
settings, generated at startup if unset). Helpers in `petpulse/auth.py` (Track A):
`current_user() -> User(uid, name)` and `require_pet_access(pet_id) -> Pet` (404 unless user in pet.owners).
Until Track A merges, other tracks may import these names; if missing on your branch, add your code
behind them anyway and note it; do NOT create your own petpulse/auth.py.

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
Legacy routes in api_server.py stay mounted but are auth+ownership protected (Track A).

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
webm, ogg, mp4, wav (sniffed from the bytes; `audio/webm;codecs=opus` etc. are fine). Samples:
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
- Raise errors with `petpulse.errors` (`NotFoundError`, `UnprocessableError(detail, code=...)`,
  `BadGatewayError`, `UnsupportedMediaTypeError`, `PayloadTooLargeError`, ...). They are
  `HTTPException`s; plain `HTTPException` also gets the same body.

### Using the auth helpers (backend tracks)
```python
from petpulse.auth import Pet, User, current_user, require_pet_access

@router.get("/api/pets/{pet_id}/notes")
def list_notes(pet: Pet = Depends(require_pet_access)): ...        # pet.id, pet.owners, ...

@router.get("/api/voice/samples")
def samples(user: User = Depends(current_user)): ...
```
`tests/test_auth.py` walks the OpenAPI schema: every new `/api` route automatically gets the
401 (no/bad token) check, and every route with `{pet_id}` the 404-for-another-user check. New
routes must therefore use one of the two dependencies (or be added to the public list there,
which needs a reason).

Test fixtures: `client` is signed in as `alice` (the default owner for `make_pet()`),
`anon_client` has no credentials, `client_as("bob")` signs in as anyone.

### Data layout (Store)
- `users/{uid}`: `{name, email, demo, created_at}`.
- `pets/{id}`: `{name, animal_type, breed, age, weight, gender, owners, created_by, created_at,
  schema_version: 2}`; `id` is a uuid4. No `pages`, no `default-page`. Helpers in
  `petpulse/pets.py` (`create_pet`, `get_pet`, `list_pets`, `is_owner`, `to_pet`).
- Per-pet data stays in sub-collections: `analytics`, `notes`, `textinput`, `voice-notes`,
  `records`.
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
  `pets/{id}/notes`, and mirrored to the legacy `textinput` / `voice-notes` collections (with
  `note_id`) for the current UI. Track C: switch the mirror off with
  `petpulse.seed.LEGACY_NOTE_MIRROR = False` once nothing reads the legacy collections.

### Legacy routes
Still mounted, now protected: `{pet_id}` routes use `require_pet_access`; routes that name the
pet in a body/form (`/api/upload_pdf`, `POST /api/markdown`) need `pet` owned by the caller and
`uid` (if sent) equal to the caller; `GET /api/markdown?pet=` checks the pet. Removed: `/api/test`,
`/api/pages/invite`, `GET|POST /api/pages/{page_id}`, and (Track D, review C5) the
server-microphone routes `/api/start`, `/api/start_recording`, `/api/stop_recording`,
`/api/recording_status`; voice goes through `POST /api/pets/{pet_id}/voice-notes`. Markdown is
stored on the pet only (`page` is ignored). Their bodies raise `HTTPException` (Track B
converted the old `{"error": ...}`-with-200 bodies), so errors use the shared envelope.
`POST /api/pets/{pet_id}/analytics/{category}` and `GET /api/pets/{pet_id}/analytics` exist both
as legacy routes and in `petpulse/routers/analytics.py`; the legacy ones are registered first and
delegate to the router, both carry the pet-access check.

Records and analytics routers import `require_pet_access` from `petpulse.auth` directly (the
temporary `_auth_bridge` and `tests/_track_b_auth.py` are gone); the route-inventory test in
`tests/test_auth.py` reads the OpenAPI schema, so every new `/api/pets/{pet_id}/...` route is
checked for 401 (no token) and 404 (another user's pet) automatically.
