"""Repository layout (Track F): what lives at the root, where the backend, locks and docs are,
and that no doc, config or CI file still points at a moved or deleted file."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Tracked top-level entries. Dotfiles are tool config that has to sit at the root.
ROOT_ALLOWED = {
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
    "pyproject.toml",
    ".env.example",
    ".github",
    "firestore.rules",
    "storage.rules",
    "firebase.json",  # Firebase CLI config; must sit at the root and points at the two rules files
    "public",
    "petpulse",
    "tests",
    "evals",
    "scripts",
    "docs",
    "requirements",
    ".gitignore",
    ".dockerignore",
    ".flake8",
    ".secrets.baseline",
}

DELETED = (
    "api_server.py",
    "firestore_store.py",
    "summarize_openai.py",
    "intelligent_chatbot_service.py",
    "simple_rag_service.py",
    "pdf_parser.py",
    "ai_analytics.py",
    "visualization_service.py",
    "setup.py",
    "QUICK_START.md",
    "assets",
    "requirements.txt",
    "requirements.in",
    "requirements-dev.txt",
    "requirements-dev.in",
    "requirements-live.txt",
    "requirements-live.in",
    "petpulse/store/firestore_compat.py",
    "petpulse/routers/legacy.py",
    "petpulse/samples",
    *(f"petpulse/{m}.py" for m in ("config", "auth", "errors", "deps", "firebase", "timeutil", "pets", "audio")),
    # Review C5: recording happens in the browser; the server never opens a microphone.
    "transcribe.py",
    "main.py",
    "gcloud_auth.py",
)

# Anything a reader (or a tool) would follow to a file or name that no longer exists.
STALE = re.compile(
    r"(?<![\w/.-])("
    r"api_server|firestore_store\.py|summarize_openai|intelligent_chatbot_service|simple_rag_service"
    r"|pdf_parser|ai_analytics|visualization_service|setup\.py|QUICK_START|assets/"
    r"|requirements\.(txt|in)|requirements-(dev|live)|firestore_compat|legacy_chat|LegacyTask"
    r"|LEGACY_NOTE_MIRROR|BODY_PET_ACCESS|test_bugfixes|test_ai_analytics|test_basic|test_track_c\w*"
    r")\b"
    r"|petpulse/(config|auth|errors|deps|firebase|timeutil|pets|audio)\.py"
    r"|petpulse\.(config|auth|errors|deps|firebase|timeutil|pets|audio)\b"
    r"|petpulse/samples|petpulse\.samples|tests/test_\w+|routers/legacy\.py|routers\.legacy\b"
)


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [path for path in out.splitlines() if (ROOT / path).exists()]


def _doc_and_config_files() -> list[str]:
    names = {"Dockerfile", "Makefile", ".env.example", ".dockerignore", ".flake8", "firestore.rules", "storage.rules"}
    suffixes = (".md", ".yml", ".yaml", ".toml", ".json", ".in")
    return [
        path
        for path in _tracked()
        if not path.startswith("public/vendor/")
        and path != ".secrets.baseline"
        and (Path(path).name in names or path.endswith(suffixes))
    ]


def test_root_holds_only_the_allowed_entries():
    top = {path.split("/", 1)[0] for path in _tracked()}
    assert top - ROOT_ALLOWED == set(), "unexpected files at the repo root"
    for required in ("README.md", "LICENSE", "Dockerfile", "pyproject.toml", "petpulse", "public", "requirements"):
        assert required in top


@pytest.mark.parametrize("path", DELETED)
def test_moved_or_deleted_paths_are_gone(path):
    assert not (ROOT / path).exists(), f"{path} should be gone (moved or deleted in Track F)"


def test_backend_packages():
    pkg = ROOT / "petpulse"
    for sub in ("core", "routers", "services", "llm", "providers", "store", "schemas", "seed"):
        assert (pkg / sub / "__init__.py").is_file(), f"petpulse/{sub} must be a package"
    for module in ("config", "auth", "errors", "logging"):
        assert (pkg / "core" / f"{module}.py").is_file()
    assert (pkg / "services" / "pdf_text.py").is_file()  # per-page PDF extraction


def test_app_module_has_no_route_bodies():
    """petpulse/app.py only builds the app: no @app/@router route decorators, no handlers."""
    tree = ast.parse((ROOT / "petpulse" / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = ast.unparse(target)
                assert not re.match(r"\w+\.(get|post|put|patch|delete|api_route|route)$", name), name
    from petpulse import app as app_module

    assert [r.__name__ for r in app_module.ROUTERS], "routers are registered from petpulse/routers"


def test_tests_are_split():
    assert (ROOT / "tests" / "unit").is_dir() and (ROOT / "tests" / "integration").is_dir()
    assert list((ROOT / "tests" / "js").glob("*.test.mjs"))
    flat = [p.name for p in (ROOT / "tests").glob("test_*.py")]
    assert flat == [], f"tests belong in tests/unit or tests/integration: {flat}"


@pytest.mark.parametrize("name", ["base", "dev", "live"])
def test_requirements_are_pinned_locks(name):
    lock = (ROOT / "requirements" / f"{name}.txt").read_text(encoding="utf-8").lower()
    assert (ROOT / "requirements" / f"{name}.in").is_file(), "each lock keeps its .in source"
    assert f"uv pip compile requirements/{name}.in" in lock
    pins = [line for line in lock.splitlines() if line and not line.startswith(("#", " "))]
    assert pins and all("==" in line for line in pins), f"every {name} requirement must be pinned"


def test_base_requirements_content():
    base = (ROOT / "requirements" / "base.txt").read_text(encoding="utf-8").lower()
    assert "\nfastapi==" in base
    assert "\nopenai==" in base  # shipped in base, imported lazily
    for removed in ("pandas", "numpy", "pyaudio", "firebase-admin"):
        assert f"\n{removed}==" not in base, f"{removed} should not be a base dependency"


def test_entry_points_use_the_new_paths():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '"petpulse.app:app"' in dockerfile
    assert "requirements/base.txt" in dockerfile and "requirements/live.txt" in dockerfile
    assert "petpulse.app:app" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "petpulse.app:app" in (ROOT / "Makefile").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "requirements/base.txt" in ci and "requirements/dev.txt" in ci
    assert "per-file-ignores" not in (ROOT / ".flake8").read_text(encoding="utf-8")


def test_docs_folder():
    docs = ROOT / "docs"
    for name in ("api-contract.md", "live-smoke.md", "firebase.md", "quick-start.md"):
        assert (docs / name).is_file(), name
    assert list((docs / "images").glob("*.png")), "README screenshots live in docs/images/"


def test_no_doc_or_config_mentions_a_moved_or_deleted_file():
    hits = []
    for path in _doc_and_config_files():
        for number, line in enumerate((ROOT / path).read_text(encoding="utf-8").splitlines(), 1):
            if STALE.search(line):
                hits.append(f"{path}:{number}: {line.strip()}")
    assert hits == [], "\n".join(hits)


def test_markdown_links_resolve():
    link = re.compile(r"\]\(([^)\s]+)\)|<img [^>]*src=\"([^\"]+)\"")
    broken = []
    for path in _tracked():
        if not path.endswith(".md") or path.startswith("public/vendor/"):
            continue
        source = ROOT / path
        for match in link.finditer(source.read_text(encoding="utf-8")):
            target = (match.group(1) or match.group(2)).split("#", 1)[0]
            if not target or re.match(r"[a-z]+:", target):
                continue
            if not (source.parent / target).exists():
                broken.append(f"{path} -> {target}")
    assert broken == [], broken


def test_readme():
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PetPulse" in content and len(content) > 100
    assert "uvicorn petpulse.app:app" in content


def test_public_directory():
    for name in ("index.html", "main.html", "styles.css"):
        assert (ROOT / "public" / name).is_file(), name


def test_pyproject_toml():
    content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.black]" in content and "line-length" in content


def test_gitignore():
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "gcloud-key.json", "__pycache__"):
        assert pattern in content


def test_template_files():
    assert (ROOT / ".env.example").is_file()
    # Firebase web config is served by GET /api/auth/config; no client config file/template.
    assert not (ROOT / "public" / "firebase-config.template.js").exists()


def test_no_sensitive_files():
    for name in (".env", "gcloud-key.json"):
        assert not (ROOT / name).exists(), f"Sensitive file found: {name}"
    assert not (ROOT / "public" / "firebase-config.js").exists()
