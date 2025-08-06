# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Daemon (runs in Docker)
**The Python daemon always runs in Docker containers, never directly on the host system.**

```bash
# Build daemon Docker image
docker build -t codechat:latest .

# Build and run tests (primary way to test the daemon)
docker build --target test -t codechat:test .
docker run codechat:test

# Install CodeChat in target repository (creates Docker Compose setup)
./scripts/install/install-codechat.sh  # Linux/Mac
./scripts/install/install-codechat.ps1  # Windows

# Start daemon in target repository (runs Docker container on port 16005)
./.codechat/codechat.sh     # Linux/Mac
./.codechat/codechat.ps1    # Windows
```

### Local Development (Poetry - for daemon development only)
For daemon development, you can use Poetry locally, but deployment is always Docker:

```bash
# Install dependencies for development
cd daemon && poetry install

# Run tests locally during development
cd daemon && poetry run pytest

# Lint and type checking
cd daemon && poetry run ruff check
cd daemon && poetry run mypy codechat

# Start daemon locally for development (production uses Docker)
cd daemon && poetry run codechat start --host 0.0.0.0 --port 16005
```

### VS Code Extension (runs in VS Code)
The VS Code extension runs in VS Code and communicates with the Dockerized daemon via HTTP API:

```bash
# Install dependencies
cd vscode-extension/CodeChat && npm install

# Compile TypeScript
cd vscode-extension/CodeChat && npm run compile

# Watch mode for development
cd vscode-extension/CodeChat && npm run watch

# Run tests
cd vscode-extension/CodeChat && npm test

# Lint code
cd vscode-extension/CodeChat && npm run lint
```

## Architecture Overview

CodeChat is a local-first AI assistant that integrates multiple LLM providers with your codebase. The architecture consists of three main components:

### 1. VS Code Extension (`vscode-extension/CodeChat/`)
- **Entry Point**: `src/extension.ts`
- **Communication**: HTTP/REST calls to daemon on `http://localhost:16005`
- **Features**: Chat panel, inline autocomplete, quick-fix actions
- **Configuration**: Daemon URL configurable via VS Code settings (`codechat.daemonUrl`)

### 2. Python Daemon (`daemon/codechat/`)
The daemon provides the core intelligence and runs as a FastAPI server:

- **`server.py`**: FastAPI application with `/health` and `/query` endpoints
- **`indexer.py`**: File watching and vector embedding using OpenAI's text-embedding-3-small
- **`vector_db.py`**: FAISS-based vector storage with metadata tracking
- **`llm_router.py`**: Routes requests to different LLM providers, handles context injection
- **`dep_graph.py`**: Dependency graph analysis using tree-sitter
- **`watcher.py`**: File system monitoring for real-time indexing
- **`models.py`**: Pydantic models for API contracts (QueryRequest, ChatMessage, Snippet, etc.)

### 3. LLM Provider Integrations (`daemon/codechat/providers/`)
Pluggable backends supporting:
- OpenAI (`openai.py`)
- Anthropic (`anthropic.py`)
- Google (`google.py`)
- Azure (`azure.py`)

## Key Data Flow

1. VS Code extension sends `QueryRequest` to daemon `/query` endpoint
2. `LLMRouter` processes request and enriches with context:
   - Vector similarity search for relevant code snippets
   - Dependency graph analysis for related files
   - File content injection based on request context
3. Request forwarded to appropriate LLM provider
4. Response streamed back to VS Code extension

## Configuration

- **Daemon Config**: Managed via `config.py`, supports environment variables
- **VS Code Settings**: `codechat.daemonUrl` (default: `http://localhost:16005`)
- **Cache Directory**: `/config/.cache/codechat` for vector DB persistence
- **Embedding Model**: Uses OpenAI's `text-embedding-3-small` (configured in `indexer.py:24`)

## Testing Strategy

- **Unit Tests**: `daemon/tests/unit/` (pytest-based)
- **Integration Tests**: `daemon/tests/integration/`
- **VS Code Extension Tests**: Jest-based in `vscode-extension/CodeChat/`
- **Docker Test Target**: Multi-stage build with dedicated test stage

## Development Notes

- The daemon requires API keys for LLM providers (configured via environment variables)
- Vector embeddings are cached and persisted across daemon restarts
- File watching uses `watchdog` library for cross-platform compatibility
- Git integration available when GitPython is installed (optional dependency)
- Structured logging via `structlog` throughout the daemon
- **Git Commands**: When using git commands in WSL/Linux environment, use `git.exe` instead of `git` to ensure proper integration with Windows Git credentials