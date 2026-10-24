# Contributing to Autonomous AI Coding Agent

We welcome contributions to improve the agent's reasoning capabilities, sandbox isolation, and developer experience.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/autonomous-ai-coding-agent.git
   cd autonomous-ai-coding-agent
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```

## Running Tests

Execute the automated test suite:
```bash
pytest -v
```

All new features and bug fixes must include unit or integration test coverage.

## Code Standards

- **Type Hints**: Include type hints for all public functions, classes, and methods.
- **Pydantic Models**: Use Pydantic schemas for data validation and API input/output models.
- **Security**: Never allow untrusted code execution on the host machine. Always enforce Docker sandbox controls.
- **Logging**: Use Python's built-in `logging` library instead of `print()` statements in core libraries.
