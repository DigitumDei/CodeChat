# CodeChat
Integrate multi LLM with your code locally, and integrate that with CLI and VS Code

# High-level Architecture
```text
┌───────────────────────────┐
│        VS Code UI         │  (chat panel, inline autocomplete,
│  Code Chat extension      │   quick‑fix actions)               │
└────────────┬──────────────┘
             │ JSON‑RPC / WebSocket
┌────────────▼──────────────┐
│      Code Chat Daemon     │   ← runs locally, started either
│  (CLI ‑or‑ Docker image)  │      by `codechat` CLI *or* the
│                           │      VS Code extension
│  ▸ Indexer / Watcher      │
│  ▸ Vector‑DB + Dep‑graph  │
│  ▸ LLM Router / Prompting │
└────────────┬──────────────┘
             │ REST / gRPC (future: language‑server‑style protocol)
┌────────────▼──────────────┐
│  pluggable LLM back‑ends  │  (OpenAI, Anthropic, Ollama, LM Studio,
│  & tool runners           │   or your own containerised model)      │
└───────────────────────────┘
```
```
# Folder Layout
.
│   .dockerignore
│   Dockerfile
│   LICENSE
│   README.md
│
├───.github
│   └───workflows
├───daemon
│   │   poetry.lock
│   │   pyproject.toml
│   │
│   └───codechat
│           __init__.py
│
├───scripts
│       dev‑alias.sh
│       doctor.sh
│
└───vscode-extension
```
