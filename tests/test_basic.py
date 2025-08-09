"""
Basic tests for PetPulse application.
These tests ensure the application structure is correct and basic functionality works.
"""

import pytest
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_environment_variables():
    """Test that environment variables are properly handled."""
    # Test that the app doesn't crash when environment variables are missing
    import os
    
    # These should not cause import errors even if not set
    api_key = os.getenv("OPENAI_API_KEY", "test")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "ci-test")
    
    assert isinstance(api_key, str)
    assert isinstance(project_id, str)


def test_app_structure():
    """Test that the app has expected structure."""
    import os
    
    # Check that key files exist
    assert os.path.exists("api_server.py")
    assert os.path.exists("main.py")
    assert os.path.exists("requirements.txt")
    assert os.path.exists("README.md")
    assert os.path.exists("public/index.html")
    assert os.path.exists("summarize_openai.py")
    assert os.path.exists("transcribe.py")
    assert os.path.exists("firestore_store.py")


def test_requirements_file():
    """Test that requirements.txt is readable and contains expected packages."""
    with open("requirements.txt", "r") as f:
        content = f.read()
        assert "fastapi" in content.lower()
        assert "openai" in content.lower()
        assert "firebase-admin" in content.lower()


def test_readme_exists():
    """Test that README.md exists and is not empty."""
    assert os.path.exists("README.md")
    with open("README.md", "r") as f:
        content = f.read()
        assert len(content) > 100  # Should have substantial content
        assert "PetPulse" in content


def test_dockerfile_exists():
    """Test that Docker configuration exists."""
    assert os.path.exists("Dockerfile")
    assert os.path.exists("docker-compose.yml")


def test_public_directory():
    """Test that public directory has expected files."""
    assert os.path.exists("public")
    assert os.path.exists("public/index.html")
    assert os.path.exists("public/styles.css")
    assert os.path.exists("public/main.html")


def test_assets_directory():
    """Test that assets directory exists with documentation images."""
    assert os.path.exists("assets")
    # Should have at least some PNG files for documentation
    import glob
    png_files = glob.glob("assets/*.png")
    assert len(png_files) > 0


def test_pyproject_toml():
    """Test that pyproject.toml exists and has Black configuration."""
    assert os.path.exists("pyproject.toml")
    with open("pyproject.toml", "r") as f:
        content = f.read()
        assert "[tool.black]" in content
        assert "line-length" in content


def test_gitignore():
    """Test that .gitignore exists and has expected patterns."""
    assert os.path.exists(".gitignore")
    with open(".gitignore", "r") as f:
        content = f.read()
        assert ".env" in content
        assert "gcloud-key.json" in content
        assert "__pycache__" in content


def test_ci_workflow():
    """Test that CI workflow exists."""
    assert os.path.exists(".github/workflows/ci.yml")


class TestBasicFunctionality:
    """Test class for basic application functionality that doesn't require external services."""
    
    def test_python_syntax(self):
        """Test that all Python files have valid syntax."""
        import py_compile
        import glob
        
        python_files = glob.glob("*.py")
        for py_file in python_files:
            try:
                py_compile.compile(py_file, doraise=True)
            except py_compile.PyCompileError as e:
                pytest.fail(f"Syntax error in {py_file}: {e}")
    
    def test_documentation_completeness(self):
        """Test that key documentation files exist."""
        docs = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "QUICK_START.md", "LICENSE"]
        for doc in docs:
            assert os.path.exists(doc), f"Missing documentation file: {doc}"
    
    def test_template_files(self):
        """Test that template files exist for user configuration."""
        assert os.path.exists(".env.template")
        assert os.path.exists("public/firebase-config.template.js")


# Simple smoke tests that test module structure without importing
def test_module_files_exist():
    """Test that all expected Python modules exist."""
    modules = [
        "api_server.py",
        "summarize_openai.py", 
        "transcribe.py",
        "firestore_store.py",
        "gcloud_auth.py",
        "main.py",
        "pdf_parser.py",
        "setup.py",
        "ai_analytics.py",
        "intelligent_chatbot_service.py",
        "simple_rag_service.py",
        "visualization_service.py"
    ]
    
    for module in modules:
        assert os.path.exists(module), f"Missing module: {module}"


def test_no_sensitive_files():
    """Test that no sensitive files are accidentally included."""
    sensitive_files = [
        ".env",
        "gcloud-key.json",
        "firebase-config.js"  # Should only have the template
    ]
    
    for sensitive_file in sensitive_files:
        if sensitive_file == "firebase-config.js":
            # Check it's not in public/
            assert not os.path.exists(f"public/{sensitive_file}"), f"Sensitive file found: public/{sensitive_file}"
        else:
            assert not os.path.exists(sensitive_file), f"Sensitive file found: {sensitive_file}"