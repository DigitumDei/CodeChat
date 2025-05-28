# daemon/codechat/dep_graph.py
import ast
import pathlib
import networkx as nx

class DepGraph:
    """Builds a directed graph of `module → dependency` edges."""
    def __init__(self):
        self.graph = nx.DiGraph()

    def build(self, files: list[pathlib.Path]) -> None:
        self.graph.clear()
        for path in files:
            if path.suffix != ".py":                 # only Python for now
                continue
            mod = path.stem
            imports = self._imports(path)
            for dep in imports:
                self.graph.add_edge(mod, dep)

    # ---------- helpers -------------------------------------------------
    def _imports(self, path: pathlib.Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf‑8"))
        deps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for n in node.names:
                    deps.add(n.name.split(".")[0])   # top‑level package
        return deps
