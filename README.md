# CodeChat
Integrate multi LLM with your code locally, and integrate that with CLI and VS Code

# High-level Architecture
```mermaid
flowchart TB
    subgraph VSCodeUI["VS Code UI"]
      direction TB
      A["Chat panel, inline autocomplete, quick‑fix actions"]
    end
    subgraph Daemon["Code Chat Daemon (CLI‑or‑Docker image)"]
      direction TB
      B[Indexer / Watcher]
      C[Vector‑DB + Dep‑graph]
      D[LLM Router / Prompting]
    end
    subgraph Backends["Pluggable LLM back‑ends & tool runners"]
      direction TB
      E["OpenAI, Anthropic, Ollama, LM Studio, or your own containerised model"]
    end

    VSCodeUI -- "JSON‑RPC / WebSocket" --> Daemon
    Daemon -- "REST / gRPC (future: language‑server‑style protocol)" --> Backends
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
