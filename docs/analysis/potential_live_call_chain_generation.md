# Potential Live Call Chain Generation

## Overview

The goal is to support **multi-language function-level call chain analysis** that can be computed *on demand* ("live") from a given starting function, traversing a configurable number of steps through its dependencies and dependents.

The current system already:

- Maintains a **file-level dependency graph** using Tree-sitter for parsing imports/includes across multiple languages.
- Updates this dependency graph incrementally on file changes.

This document outlines how to extend the system to:

1. Support **function/method-level call graph extraction**.
2. Combine this fine-grained graph with the existing file-level graph.
3. Generate *live* N-step call chains from an arbitrary starting point.

---

## High-Level Architecture

### 1. Extend Parsing to Function-Level

- For each supported language, define Tree-sitter queries that:
  - Identify **function/method definitions** (name, location, containing file).
  - Identify **function/method calls** (caller, callee, location).
- This yields per-file call graphs with edges `(function_A -> function_B)`.

Example for Python (Tree-sitter query snippet):

```scheme
(call
  function: (identifier) @callee)
```

### 2. Store Call Graph Data

- Maintain a `FunctionDepGraph` (NetworkX DiGraph or similar) where:
  - Node: Fully qualified function identifier (e.g., `file_stem:function_name`).
  - Edge: `caller -> callee`.
- This graph can be updated incrementally:
  - When a file changes, remove its old function nodes and edges.
  - Re-parse the file to extract updated function definitions/calls.

### 3. Integrate With File-Level Graph

- The **file dependency graph** tells us which files might contain the callee definitions.
- The **function dependency graph** tells us which functions call which.
- Together, they allow:
  - Narrowing search to only relevant files.
  - Traversing call chains across files without scanning unrelated code.

### 4. Live N-Step Traversal

When a request for a call chain comes in:

1. Start at the specified function.
2. Perform a breadth-first or depth-first traversal up to *N* edges away.
3. Use the dependency graphs to resolve:
   - Calls within the same file.
   - Cross-file calls via file dependencies.
4. Return a structured list/tree of calls, optionally with:
   - Source locations.
   - Snippets or documentation comments.

Example output:

```json
{
  "start": "process_order",
  "steps": [
    {
      "caller": "process_order",
      "callee": "validate_customer",
      "file": "orders.py",
      "line": 42
    },
    {
      "caller": "validate_customer",
      "callee": "get_customer_data",
      "file": "customers.py",
      "line": 18
    }
  ]
}
```

---

## Performance Considerations

- **Incremental updates**: Avoid full re-parsing on each query; store the function graph in memory and update only affected files.
- **On-demand resolution**: Do not precompute transitive chains; compute them live using graph traversal algorithms.
- **Graph indexing**: Use maps for `function_name -> node_id` lookups for quick starting point resolution.
- **Scope limiting**: Restrict traversals to files/functions within the dependency subgraph relevant to the starting point.

---

## Potential Enhancements

- Add **symbol resolution** to handle overloaded names, imports with aliases, etc.
- Store **type information** (if language allows) to improve cross-file call resolution.
- Support **reverse call chains** (find all functions that call X).
- Output call chains as interactive visualizations (e.g., D3.js graph, Graphviz).

---

## Next Steps

1. Define Tree-sitter queries for function definitions and calls for each language in `LANGUAGE_DEFINITIONS`.
2. Implement `FunctionDepGraph` alongside the existing `DepGraph`.
3. Modify `Indexer` to update both graphs on file events.
4. Implement API endpoint `/callchain` that:
   - Accepts starting function and depth.
   - Returns computed call chain.

