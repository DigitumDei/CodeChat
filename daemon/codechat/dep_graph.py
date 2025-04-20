import networkx as nx

class DepGraph:
    """Manages dependency graph of project modules"""
    def __init__(self):
        self.graph = nx.DiGraph()

    def build(self, files: list):
        # parse imports, build nodes and edges
        pass