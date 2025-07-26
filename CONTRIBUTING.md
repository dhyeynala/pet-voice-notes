# 🤝 Contributing to PetPages

Thank you for your interest in contributing to PetPages! This document provides guidelines and information for contributors.

## 🚀 Quick Start

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/final_github.git`
3. **Create** a feature branch: `git checkout -b feature/amazing-feature`
4. **Make** your changes
5. **Test** your changes: `python -m pytest`
6. **Commit** your changes: `git commit -m 'Add amazing feature'`
7. **Push** to your branch: `git push origin feature/amazing-feature`
8. **Open** a Pull Request

## 📋 Development Setup

### Prerequisites
- Python 3.8+
- Git
- API Keys (see [QUICK_START.md](QUICK_START.md))

### Local Development
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/final_github.git
cd final_github

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies

# Setup environment
cp .env.template .env
# Edit .env with your API keys

# Setup Firebase
cp public/firebase-config.template.js public/firebase-config.js
# Edit firebase-config.js with your Firebase details

# Run development server
python api_server.py
```

## 🧪 Testing

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_api_server.py

# Run with verbose output
pytest -v
```

### Writing Tests
- Tests should be in the `tests/` directory
- Use descriptive test names
- Test both success and failure cases
- Mock external API calls

Example test:
```python
import pytest
from api_server import app

def test_health_endpoint():
    with app.test_client() as client:
        response = client.get('/api/health')
        assert response.status_code == 200
        assert response.json['status'] == 'healthy'
```

## 🔍 Code Quality

### Linting
```bash
# Run flake8
flake8 .

# Run black (code formatting)
black .

# Run isort (import sorting)
isort .
```

### Pre-commit Hooks
```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## 📝 Code Style

### Python
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use type hints where appropriate
- Write docstrings for functions and classes
- Keep functions small and focused

### JavaScript
- Use ES6+ features
- Follow consistent naming conventions
- Add JSDoc comments for functions

### HTML/CSS
- Use semantic HTML
- Follow BEM methodology for CSS
- Ensure accessibility standards

## 🐛 Bug Reports

### Before Submitting
1. Check existing issues
2. Try to reproduce the bug
3. Check if it's a configuration issue

### Bug Report Template
```markdown
**Bug Description**
Brief description of the bug

**Steps to Reproduce**
1. Step 1
2. Step 2
3. Step 3

**Expected Behavior**
What should happen

**Actual Behavior**
What actually happens

**Environment**
- OS: [e.g., macOS, Windows, Linux]
- Python Version: [e.g., 3.11]
- Browser: [e.g., Chrome, Firefox]

**Additional Context**
Any other relevant information
```

## 💡 Feature Requests

### Before Submitting
1. Check if the feature already exists
2. Consider if it aligns with project goals
3. Think about implementation complexity

### Feature Request Template
```markdown
**Feature Description**
Brief description of the feature

**Use Case**
Why this feature would be useful

**Proposed Implementation**
How you think it could be implemented

**Alternatives Considered**
Other approaches you considered

**Additional Context**
Any other relevant information
```

## 🔧 Pull Request Guidelines

### Before Submitting
- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] No sensitive data committed

### PR Template
```markdown
**Description**
Brief description of changes

**Type of Change**
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

**Testing**
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] Manual testing completed

**Screenshots** (if applicable)
Add screenshots for UI changes

**Checklist**
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No sensitive data committed
```

## 🏗️ Architecture

### Project Structure
```
final_github/
├── api_server.py              # Main FastAPI server
├── main.py                    # Core application logic
├── intelligent_chatbot_service.py  # AI chatbot service
├── simple_rag_service.py      # RAG-based AI service
├── visualization_service.py    # Chart generation service
├── ai_analytics.py           # Analytics AI service
├── transcribe.py             # Voice transcription
├── firestore_store.py        # Database operations
├── gcloud_auth.py           # Google Cloud authentication
├── pdf_parser.py            # PDF processing
├── summarize_openai.py      # OpenAI summarization
├── public/                  # Frontend files
│   ├── index.html
│   ├── main.html
│   ├── styles.css
│   └── firebase-config.js
├── tests/                   # Test files
├── requirements.txt         # Python dependencies
└── docs/                   # Documentation
```

### Key Components
- **API Server**: FastAPI-based REST API
- **AI Services**: OpenAI-powered intelligent services
- **Database**: Firebase Firestore for data storage
- **Frontend**: HTML/CSS/JavaScript interface
- **Voice Processing**: Google Cloud Speech-to-Text

## 🛡️ Security

### Guidelines
- Never commit API keys or secrets
- Use environment variables for configuration
- Validate all user inputs
- Follow OWASP security guidelines
- Report security issues privately

### Security Issues
For security issues, please email [your-email] instead of creating a public issue.

## 📚 Documentation

### Writing Documentation
- Use clear, concise language
- Include code examples
- Keep documentation up to date
- Use markdown formatting

### Documentation Structure
- `README.md`: Project overview and setup
- `QUICK_START.md`: Quick setup guide
- `SECURITY.md`: Security guidelines
- `CONTRIBUTING.md`: This file
- `docs/`: Detailed documentation

## 🏷️ Versioning

We use [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

## 📄 License

By contributing to PetPages, you agree that your contributions will be licensed under the same license as the project.

## 🙏 Recognition

Contributors will be recognized in:
- Project README
- Release notes
- Contributor hall of fame

## 🆘 Getting Help

- 📖 Check the [README.md](README.md)
- 🔍 Search existing issues
- 💬 Ask questions in discussions
- 📧 Contact maintainers

---

**Thank you for contributing to PetPages! 🐾** 