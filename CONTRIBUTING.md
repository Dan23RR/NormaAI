# Contributing to NormaAI

Thank you for your interest in contributing to NormaAI! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/normaai.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Set up the development environment (see README.md)

## Development Setup

```bash
# Install backend dependencies
poetry install

# Install frontend dependencies
cd frontend && npm ci && cd ..

# Start infrastructure
docker compose up -d postgres qdrant redis

# Generate JWT keys
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem

# Configure environment
cp .env.example .env
# Edit .env with your values

# Initialize database
alembic upgrade head

# Run the server
uvicorn src.api.main:app --reload
```

## Code Standards

### Python (Backend)

- **Formatter:** ruff format (line length 100)
- **Linter:** ruff check
- **Type checker:** mypy (strict mode)
- **Docstrings:** Required for all public modules, classes, and functions
- **Tests:** pytest with async support

```bash
# Check your code before committing
ruff check src/ tests/
ruff format src/ tests/
mypy src/ --ignore-missing-imports --no-strict-optional
pytest tests/ -v --cov=src
```

### TypeScript (Frontend)

- **Framework:** Next.js 14 with App Router
- **Style:** Tailwind CSS
- **Type checking:** strict TypeScript
- **Tests:** vitest

```bash
cd frontend
npx tsc --noEmit
npx vitest run
npm run build
```

## Submitting Changes

1. Ensure all tests pass locally
2. Write clear, descriptive commit messages
3. Push to your fork and open a Pull Request
4. Describe what your PR does and why
5. Link any related issues

### Commit Messages

Use conventional commit style:

- `feat: add CSRD Article 29 threshold detection`
- `fix: correct EUR-Lex SPARQL query for amendments`
- `docs: update API endpoint documentation`
- `test: add integration tests for gap analysis`
- `refactor: extract LLM retry logic into shared module`

## Areas for Contribution

We welcome contributions in these areas:

- **New EU frameworks:** Adding support for additional regulatory frameworks
- **Retrieval quality:** Improving hybrid search accuracy and chunking strategies
- **Frontend:** Dashboard components, visualizations, UX improvements
- **Testing:** Expanding test coverage, adding integration tests
- **Documentation:** API docs, usage examples, regulatory guides
- **Localization:** Improving i18n support (currently EN, IT, DE, FR)
- **Performance:** Caching, query optimization, batch processing

## Reporting Issues

When filing an issue, include:

- A clear title and description
- Steps to reproduce (if applicable)
- Expected vs actual behavior
- Python/Node version and OS

## Code of Conduct

Be respectful and constructive. We're building tools to help companies navigate complex regulations - collaboration and clarity matter.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
