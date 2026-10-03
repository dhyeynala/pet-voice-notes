# Contributing to PetPulse

Thank you for your interest in contributing to PetPulse! This document provides guidelines and information for contributors to this AI-powered pet health management platform.

## Demo build: branches, tracks and file ownership

The demo plan is being implemented in parallel tracks on top of the Phase 0 foundation
(`petpulse/` package, `Store`, provider fakes, gating CI). These rules keep the tracks from
stepping on each other.

### Branching
- `main` is not touched while the demo is built. Never push to it.
- `demo/integration` is the integration branch. After every merge it must be green in CI and
  start with `docker compose up` and **zero secrets**.
- Each track works on short-lived branches named `demo/<track>-<topic>` (for example
  `demo/auth-demo-login`), cut from the latest `demo/integration`, and opens its PR **into
  `demo/integration`** (never into `main`). Keep PRs small (see the plan's PR list).
- Rebase before merge: `git fetch origin && git rebase origin/demo/integration`, re-run
  `pytest`, `flake8 .`, `black --check .`, `mypy`. Only ever force-push your own track branch,
  and only with `--force-with-lease`. Never force-push `demo/integration` or `main`.
- Merge with "Squash and merge" or "Rebase and merge" (no merge commits), using a
  conventional-commit title (`feat(auth): ...`, `fix(charts): ...`, `test: ...`, `ci: ...`).

### Track ownership

| Track | Plan items | Owns (creates / edits / deletes) |
|---|---|---|
| **A. auth/data** | D1-1 backend, D1-2, D1-3, D1-4 backend | `petpulse/core/{auth,errors}.py`, `petpulse/services/pets.py`, `petpulse/seed/`, `petpulse/routers/{demo,pets}.py`, `petpulse/schemas/pets.py`, the CORS/errors block in `petpulse/app.py`, `_auth_headers` in `tests/conftest.py` |
| **B. bug fixes** | D2-1, D2-2, D2-3, D2-5, D2-6 | `petpulse/routers/records.py`, `petpulse/services/{pdf,pdf_text}.py`, `petpulse/schemas/analytics.py`, `petpulse/store/blobs.py` |
| **C. LLM layer** | D4-*, D5-*, D7-1 (LLM part) | `petpulse/llm/**`, `petpulse/services/**`, `petpulse/core/timeutil.py`, `petpulse/providers/llm.py`, `evals/**` |
| **D. voice** | D3-2, D3-3, D7-1 (STT part) | `petpulse/providers/stt.py`, `petpulse/routers/voice.py`, `petpulse/services/{voice,audio}.py`, `petpulse/seed/samples/audio/**` |
| **E. frontend** | every `public/**` change: D1-1 login UI, D1-4 banner, D2-4 XSS, D3-1 recorder, D4/D5 UI, D6-3 JS split | `public/**` (`main.html`, `index.html`, `js/`, `vendor/`). **Only this track edits `public/main.html`.** |
| **F. restructure** | repo layout | moved the backend into `petpulse/` (`petpulse/app.py`, `petpulse/core/`), split `tests/` into `unit/` and `integration/`, moved the locks to `requirements/` and the guides to `docs/`; removed the pre-contract modules and routes |
| **G. Firebase** | optional Firebase mode | `petpulse/core/firebase.py`, `petpulse/store/firestore.py`, `public/js/firebase.js`, `firestore.rules`, `storage.rules`, `docs/firebase.md` |

Docs/evals (Phase 6) and the live smoke test (Phase 7) come after the tracks above.

### Shared files (edit additively)
- **`petpulse/app.py`**: no route bodies. Put new routes in `petpulse/routers/<module>.py`
  (thin: parse, check access, call a service) and add the module to `ROUTERS`.
- **`petpulse/core/config.py`**: append new fields with a demo-safe default and add the key to
  `.env.example` (a test fails if a setting is missing there).
- **`petpulse/core/deps.py`**: add factories; don't change existing signatures. Tests use
  `deps.override(...)` / `app.dependency_overrides`.
- **`requirements/*.in` → `requirements/*.txt`**: never hand-merge a lock. On conflict take
  either side and recompile:
  `uv pip compile requirements/base.in -o requirements/base.txt --python-version 3.11`,
  `uv pip compile requirements/dev.in -c requirements/base.txt -o requirements/dev.txt --python-version 3.11`,
  `uv pip compile requirements/live.in -c requirements/base.txt -o requirements/live.txt --python-version 3.11`.
- **`tests/conftest.py`**: add fixtures, don't change existing ones without telling the other tracks.
- **`tests/integration/test_known_bugs.py`**: each review finding keeps a regression proof. If
  your PR changes a route a proof uses, update the proof in the same PR.
- **`.flake8`**: no per-file ignores. Never add codes.

### API changes that need the frontend
Backend tracks keep the old route working until the frontend PR that switches to the new one
has merged (add the new route, then the frontend switches, then a small cleanup PR removes
the old route). That keeps `demo/integration` usable at every step.

### Definition of done (every PR)
CI green (flake8, black, mypy, pytest with strict xfails, bandit, detect-secrets, docker
smoke); `docker compose up` works with no `.env`; no keys added to CI; `/api/health` still
reports every feature's mode.

## Quick Start

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/petpulse.git`
3. **Create** a feature branch: `git checkout -b feature/amazing-feature`
4. **Make** your changes
5. **Test** your changes: `python -m pytest`
6. **Commit** your changes: `git commit -m 'Add amazing feature'`
7. **Push** to your branch: `git push origin feature/amazing-feature`
8. **Open** a Pull Request

## Development Setup

### Prerequisites
- Python 3.11
- Git
- Docker (optional but recommended)
- No API keys for the demo; optional live keys are described in [docs/quick-start.md](docs/quick-start.md)

### Local Development
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/petpulse.git
cd petpulse

# Install dependencies (pinned locks in requirements/)
pip install -r requirements/base.txt -r requirements/dev.txt   # or: make install

# Optional: live settings (the demo needs no .env at all)
cp .env.example .env
# OPENAI_API_KEY for live AI; Firebase settings per docs/firebase.md
# (Firebase also needs: pip install -r requirements/live.txt)

# Run development server
uvicorn petpulse.app:app --reload   # or: make run
```

### Docker Development
```bash
# Build and run with Docker Compose
docker compose up --build

# Run specific services
docker compose up app
```

## Testing

### Running Tests
```bash
# Run all tests (Python + JS)
make test

# Python only, or one layer
pytest
pytest tests/unit
pytest tests/integration

# Run with coverage (the floor is in pyproject.toml)
pytest --cov --cov-report=html

# Run a specific test file
pytest tests/integration/test_notes_chat_insights.py

# Frontend unit/lint tests (Node 20, no npm install)
node --test tests/js/*.test.mjs
```

### Writing Tests
- `tests/unit/`: modules and services called directly, no HTTP.
- `tests/integration/`: the app over HTTP (`TestClient`), scripts and entry points.
- `tests/js/`: `node:test` tests for `public/js`.
- Shared fixtures live in `tests/conftest.py`: `client` (signed in as `alice`), `anon_client`,
  `client_as("bob")`, `make_pet()` and an isolated store per test.
- AI providers are deterministic fakes by default; never call a live API from a test.
- Use descriptive test names and cover the failure cases too (401/404/422).

Example test:
```python
def test_chat_refuses_a_dosing_question(client, make_pet):
    pet_id = make_pet(name="Max")  # owned by alice, like `client`
    response = client.post(f"/api/pets/{pet_id}/chat", json={"message": "What dose of ibuprofen?"})
    assert response.status_code == 200
    assert response.json()["status"] == "out_of_scope"
```

## Code Quality

### Linting and Formatting
These are the exact gates CI runs (`make lint`; tool versions are pinned in `requirements/dev.txt`):
```bash
flake8 .                 # config in .flake8
black --check .          # config in pyproject.toml
mypy                     # strict, on petpulse/
pytest --cov             # coverage floor in pyproject.toml
bandit -ll -r petpulse scripts evals
git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline
```

## Code Style Guidelines

### Python
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use type hints for all function parameters and return values
- Write comprehensive docstrings for functions and classes
- Keep functions small and focused (max 50 lines)
- Use async/await for I/O operations
- Handle exceptions gracefully with proper error messages

Example:
```python
async def process_voice_note(audio_data: bytes, pet_id: str) -> dict:
    """
    Process voice recording and generate AI summary.
    
    Args:
        audio_data: Raw audio bytes from recording
        pet_id: Unique identifier for the pet
        
    Returns:
        Dict containing transcript, summary, and classification
        
    Raises:
        TranscriptionError: If audio processing fails
        AIServiceError: If OpenAI API call fails
    """
    try:
        transcript = await transcribe_audio(audio_data)
        summary = await generate_ai_summary(transcript, pet_id)
        return {"transcript": transcript, "summary": summary}
    except Exception as e:
        logger.error(f"Voice note processing failed: {e}")
        raise
```

### JavaScript
- Use ES6+ features (arrow functions, const/let, destructuring)
- Follow consistent naming conventions (camelCase for variables, PascalCase for classes)
- Add JSDoc comments for functions
- Use modern async/await instead of promises where possible

### HTML/CSS
- Use semantic HTML5 elements
- Follow BEM methodology for CSS class naming
- Ensure WCAG 2.1 accessibility standards
- Use CSS Grid and Flexbox for layouts
- Implement responsive design patterns

## Technical Contributions

### AI/ML Components
- **OpenAI Function Calling**: Extend function definitions for new chart types
- **RAG Systems**: Improve context retrieval and response generation
- **Caching**: Optimize data preloading and cache invalidation strategies
- **Visualization**: Add new chart types and customization options

### Backend Development
- **FastAPI**: Add new endpoints following RESTful conventions
- **Database**: Optimize Firestore queries and data structures
- **Performance**: Implement caching layers and async optimizations
- **Security**: Enhance input validation and authentication flows

### Frontend Development
- **Chart.js**: Create new visualization components
- **Firebase SDK**: Improve real-time data synchronization
- **UI/UX**: Enhance responsive design and accessibility
- **JavaScript**: Optimize performance and add modern features

## Bug Reports

### Before Submitting
1. Check existing issues for duplicates
2. Try to reproduce the bug consistently
3. Check if it's a configuration or setup issue
4. Test with the latest version

### Bug Report Template
```markdown
**Bug Description**
Clear and concise description of the bug

**Steps to Reproduce**
1. Go to '...'
2. Click on '...'
3. Scroll down to '...'
4. See error

**Expected Behavior**
What you expected to happen

**Actual Behavior**
What actually happened

**Environment**
- OS: [e.g., macOS 13.0, Windows 11, Ubuntu 20.04]
- Python Version: [e.g., 3.11.0]
- Browser: [e.g., Chrome 108, Firefox 107]
- Docker Version: [if applicable]

**Error Logs**
```
Paste relevant error logs here
```

**Additional Context**
Add any other context about the problem here
```

## Feature Requests

### Before Submitting
1. Check if the feature already exists or is planned
2. Consider if it aligns with project goals
3. Think about implementation complexity and maintenance burden
4. Consider backwards compatibility

### Feature Request Template
```markdown
**Feature Description**
Clear and concise description of the feature

**Problem Statement**
What problem does this feature solve?

**Use Case**
Describe the specific use case and user story

**Proposed Implementation**
How you think it could be implemented (optional)

**Technical Considerations**
- API changes required
- Database schema changes
- Frontend modifications
- Performance implications

**Alternatives Considered**
Other approaches you considered

**Additional Context**
Any other relevant information, mockups, or examples
```

## Pull Request Guidelines

### Before Submitting
- [ ] Code follows style guidelines (run pre-commit hooks)
- [ ] Tests pass locally (`pytest`)
- [ ] New tests added for new features
- [ ] Documentation updated (README, docstrings, comments)
- [ ] No sensitive data committed (API keys, credentials)
- [ ] Performance impact considered
- [ ] Backwards compatibility maintained

### PR Template
```markdown
**Description**
Brief description of changes and motivation

**Type of Change**
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Code refactoring

**Technical Details**
- Affected components: [e.g., API server, AI services, frontend]
- Database changes: [if any]
- API changes: [if any]
- Dependencies added/updated: [if any]

**Testing**
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] All tests pass
- [ ] Manual testing completed
- [ ] Performance testing completed (if applicable)

**Screenshots/Videos** (if applicable)
Add screenshots or videos for UI changes

**Checklist**
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No sensitive data committed
- [ ] Performance impact assessed
- [ ] Backwards compatibility verified
```

## Project Architecture

### Core Services
```
petpulse/
├── app.py          # create_app(): middleware, lifespan (config check, logging, seed), ROUTERS
├── core/           # config (Settings), auth, errors, logging, deps (store/provider factories),
│                   #   firebase, timeutil
├── routers/        # thin HTTP layer: health, demo, pets, records, analytics, notes,
│                   #   assistant (chat), insights, voice, legacy (pre-contract routes kept)
├── services/       # notes, assistant (chat), retrieval, insights, charts, events, queries,
│                   #   voice, audio, pdf (summaries), pdf_text (page extraction), pets
├── llm/            # client, model config, schemas, prompts/*.v1.md, fake rules
├── providers/      # llm.py and stt.py: fake, OpenAI, Google
├── store/          # Store interface + JSON/in-memory/Firestore backends, blob stores
├── schemas/        # Pydantic request/response models
└── seed/           # demo users, pets, entries, notes; samples/ (audio, PDFs)
```
Also: `public/` (UI), `tests/{unit,integration,js}`, `evals/`, `scripts/`, `docs/`,
`requirements/`.

### Technology Stack
- **Backend**: Python 3.11, FastAPI, Pydantic v2
- **AI/ML**: OpenAI GPT-4, Function Calling, RAG systems
- **Database**: Firebase Firestore with intelligent caching
- **Cloud**: Google Cloud Speech-to-Text, Firebase Storage
- **Frontend**: Vanilla JavaScript ES6+, Chart.js, responsive CSS
- **Infrastructure**: Docker, GitHub Actions CI/CD

## Security Guidelines

### Development Security
- Never commit API keys, secrets, or credentials
- Use environment variables for all configuration
- Validate and sanitize all user inputs
- Follow OWASP security guidelines
- Implement proper error handling without exposing internal details
- Use HTTPS for all external API communications

### Reporting Security Issues
For security vulnerabilities, please email the maintainers directly instead of creating a public issue. Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if available)

## Documentation Standards

### Code Documentation
- Write clear, comprehensive docstrings for all functions and classes
- Include type hints for better code clarity
- Add inline comments for complex logic
- Keep documentation up to date with code changes

### Project Documentation
- Update README.md for major feature additions
- Maintain docs/quick-start.md for setup instructions
- Document API changes in commit messages
- Create examples for new features

## Release Process

### Versioning
We follow [Semantic Versioning](https://semver.org/):
- **MAJOR** (X.0.0): Breaking changes, major architecture updates
- **MINOR** (0.X.0): New features, backwards compatible
- **PATCH** (0.0.X): Bug fixes, security patches

### Release Checklist
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Version number bumped
- [ ] Release notes prepared
- [ ] Security review completed

## License

By contributing to PetPulse, you agree that your contributions will be licensed under the MIT License that covers the project.

## Recognition

Contributors are recognized through:
- GitHub contributor statistics
- Release notes acknowledgments
- Project documentation credits

## Getting Help

- **Documentation**: Check [README.md](README.md) and [docs/quick-start.md](docs/quick-start.md)
- **Issues**: Search existing GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Direct Contact**: Email maintainers for urgent matters

---

**Thank you for contributing to PetPulse and helping improve AI-powered pet healthcare technology!**