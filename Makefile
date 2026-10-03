# PetPulse developer shortcuts. The live smoke test is the only target that can spend money,
# and only when a provider key is set in .env (see docs/live-smoke.md).

COMPOSE ?= docker compose
PYTHON ?= python
SMOKE_ARGS ?=
# Extra `docker compose run` flags, e.g. a Google service-account mount:
#   make smoke-live DOCKER_RUN_ARGS="-v $$HOME/sa.json:/secrets/sa.json:ro"
DOCKER_RUN_ARGS ?=

.PHONY: help install run test lint smoke-live smoke-live-dry smoke-live-local smoke-fake samples

help:
	@echo "make install           install the pinned base + dev requirements (requirements/)"
	@echo "make run               run the API + UI on http://localhost:8000 (uvicorn petpulse.app:app)"
	@echo "make test              pytest (tests/unit, tests/integration) + JS tests (tests/js)"
	@echo "make lint              black, flake8, mypy, bandit, detect-secrets (what CI runs)"
	@echo "make smoke-live        live smoke test in the app image (reads .env; capped by LIVE_CALL_CAP)"
	@echo "make smoke-live-dry    show providers, models and the call cap; makes no calls"
	@echo "make smoke-live-local  same as smoke-live, with the local Python environment"
	@echo "make smoke-fake        run the smoke script against the deterministic fakes (what CI does)"
	@echo "make samples           regenerate bundled audio/PDF samples (needs espeak-ng + ffmpeg)"

install:
	$(PYTHON) -m pip install -r requirements/base.txt -r requirements/dev.txt

run:
	$(PYTHON) -m uvicorn petpulse.app:app --reload --host 127.0.0.1 --port 8000

test:
	$(PYTHON) -m pytest
	node --test tests/js/*.test.mjs

lint:
	$(PYTHON) -m black --check .
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy
	$(PYTHON) -m bandit -q -ll -r petpulse scripts evals
	git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline

smoke-live:
	mkdir -p reports
	$(COMPOSE) run --rm --no-deps --user "$$(id -u):$$(id -g)" -v "$$(pwd)/reports:/app/reports" $(DOCKER_RUN_ARGS) \
		app python scripts/smoke_live.py $(SMOKE_ARGS)

smoke-live-dry:
	$(MAKE) smoke-live SMOKE_ARGS="--dry-run $(SMOKE_ARGS)"

smoke-live-local:
	$(PYTHON) scripts/smoke_live.py $(SMOKE_ARGS)

smoke-fake:
	$(PYTHON) scripts/smoke_live.py --allow-fake $(SMOKE_ARGS)

samples:
	$(PYTHON) scripts/make_samples.py
