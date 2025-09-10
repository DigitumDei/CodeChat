# AGENTS.md

This guide is for AI coding agents (e.g., Claude Code, Copilot, Cursor, Codeium, Codex CLI) working with this repository. It summarizes how to build, run, test, and reason about the CodeChat project so agents can operate safely and efficiently.

## Development Commands

### Python Daemon (runs in Docker)
The Python daemon is intended to run in Docker containers.

```bash
# Build daemon Docker image
docker build -t codechat:latest .

# Build and run tests in Docker (CI‑like environment)
docker build --target test -t codechat:test .
docker run codechat:test

# Install CodeChat into a target repository (creates .codechat folder + compose)
./scripts/install/install-codechat.sh   # Linux/Mac
./scripts/install/install-codechat.ps1  # Windows

# Start daemon in the target repository (exposes port 16005)
./.codechat/codechat.sh     # Linux/Mac
./.codechat/codechat.ps1    # Windows
```

### Local Development (Poetry – for daemon development only)
Local runs are useful during development; production use should prefer Docker.

```bash
# Install dependencies for development
cd daemon && poetry install

# Run tests locally
cd daemon && poetry run pytest

# Lint and type check
cd daemon && poetry run ruff check
cd daemon && poetry run mypy codechat

# Start daemon locally for development
cd daemon && poetry run codechat start --host 0.0.0.0 --port 16005
```

### VS Code Extension (talks to the daemon over HTTP)

```bash
# Install deps
cd vscode-extension/CodeChat && npm install

# Build / watch / test / lint
cd vscode-extension/CodeChat && npm run compile
cd vscode-extension/CodeChat && npm run watch
cd vscode-extension/CodeChat && npm test
cd vscode-extension/CodeChat && npm run lint
```

## Architecture Overview

CodeChat is a local‑first AI assistant that integrates multiple LLM providers with your codebase. It has three main parts:

### 1) VS Code Extension (`vscode-extension/CodeChat/`)
- Entry: `vscode-extension/CodeChat/src/extension.ts`
- Communicates with the daemon via HTTP/REST on `http://localhost:16005`
- Features: chat panel, inline assist, quick‑fix style actions
- Setting: `codechat.daemonUrl`

### 2) Python Daemon (`daemon/codechat/`)
FastAPI service that indexes code, maintains a dep‑graph, constructs prompts, and routes to providers.

- `daemon/codechat/server.py`: FastAPI app; endpoints: `/health`, `/query`, `/admin/reload-config`, `/dependencies`, `/debug/depgraph`
- `daemon/codechat/indexer.py`: Watches files, computes embeddings (OpenAI `text-embedding-3-small`), queries vector DB
- `daemon/codechat/vector_db.py`: FAISS‑based store with path/hash metadata persisted under `/config/.cache/codechat`
- `daemon/codechat/dep_graph.py`: Local dependency graph via tree‑sitter (Python/JS/TS/C/C++/HTML/CSS)
- `daemon/codechat/watcher.py`: Filesystem monitoring (watchdog)
- `daemon/codechat/llm_router.py`: Builds context from files or vector matches, formats prompts, routes to providers
- `daemon/codechat/prompt.py`: Provider‑specific prompt formatting
- `daemon/codechat/models.py`: Pydantic models for API contracts

### 3) LLM Provider Integrations (`daemon/codechat/providers/`)
Currently implemented:
- OpenAI (`daemon/codechat/providers/openai.py`)
- Anthropic (`daemon/codechat/providers/anthropic.py`)
- Google (`daemon/codechat/providers/google.py`)

## Key Data Flow

1. Editor or client sends `QueryRequest` to the daemon `/query` endpoint (optionally `?stream=true`).
2. `LLMRouter` enriches the request:
   - Vector similarity search over FAISS for relevant files/snippets
   - Optional dependency‑graph lookups for related files
   - Direct file content injection when `files` are specified
3. The request is sent to the selected provider; responses can stream tokens.
4. The client renders text incrementally or as a final message.

## Configuration

- Daemon config lives at `/config/config.json` and is read by `daemon/codechat/config.py`.
- Use the CLI to set keys and hot‑reload the running daemon:

```bash
# Examples (run inside the container or from the host if forwarded)
codechat config set openai.key   sk-...
codechat config set anthropic.key ...
codechat config set gemini.key   ...
```

- Logging level can be set with `CODECHAT_LOG_LEVEL` (e.g., via compose) and influences structured logs.
- Embeddings model is `text-embedding-3-small` (see `daemon/codechat/indexer.py`).

## HTTP Endpoints (daemon)

- `GET /health` – liveness probe
- `POST /query` – synchronous chat; body: `QueryRequest`
- `POST /query?stream=true` – SSE token stream
- `POST /admin/reload-config` – reloads `/config/config.json`
- `POST /dependencies` – dependency graph queries
- `GET /debug/depgraph` – graph stats and samples

For quick manual testing, see `httptest/tests.http`.

## Testing Strategy

- Unit tests: `daemon/tests/unit/`
- Integration tests: `daemon/tests/integration/`
- Docker test target: `docker build --target test ...` mirrors CI execution

## Operational Notes for Agents

- Prefer Docker for end‑to‑end validation; use Poetry only for daemon development loops.
- Do not hardcode secrets; rely on `/config/config.json` and `codechat config set ...`.
- When changing prompt formats or routing, check all providers still work (`daemon/codechat/providers/`).
- The vector DB persists under `/config/.cache/codechat`; after structural changes, consider a rebuild via reindex (restart container) to avoid stale artifacts.
- Use the dependency graph endpoints to debug relationships during prompt/context work.

## Troubleshooting

- If `/config/config.json` is missing, the daemon logs a warning and provider calls will fail until keys are set.
- If FAISS or tree‑sitter errors appear locally, validate inside Docker where dependencies are pinned.
- Use `/debug/depgraph` and `/dependencies` to verify graph contents when results look off.

