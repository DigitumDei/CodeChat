# CodeChat
Integrate multi LLM with your code locally, and integrate that with CLI and VS Code

# High-level Architecture
```mermaid
flowchart TB
    subgraph VSCodeUI["VS Code UI"]
      direction TB
      A["Chat panel, inline autocomplete, quick‑fix actions"]
    end
    subgraph Daemon["Code&nbsp;Chat&nbsp;Daemon&nbsp;(CLI‑or‑Docker&nbsp;image)"]
      direction TB
      B[Indexer / Watcher]
      C[Vector‑DB + Dep‑graph]
      D[LLM Router / Prompting]
    end
    subgraph Backends["Pluggable&nbsp;LLM&nbsp;back‑ends&nbsp;&&nbsp;tool&nbsp;runners"]
      direction TB
      E["OpenAI, Anthropic, Google, etc."]
    end

    VSCodeUI -- "HTTP / REST (JSON)" --> Daemon
    Daemon -- "HTTP / REST (JSON)" --> Backends
```

# Local Build and Install

See [docs/InstallingRunCodeChat.md](docs/InstallingRunCodeChat.md)

# VS Code Extension

See [docs/VS-Code-Extension.md](docs/VS-Code-Extension.md)