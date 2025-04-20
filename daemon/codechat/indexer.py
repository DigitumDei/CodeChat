class Indexer:
    """Watches project files and builds vector index + dependency graph"""
    def __init__(self):
        # initialize vector store, dep-graph
        pass

    def build_index(self):
        """(Re)index all files"""
        # TODO: scan files, embed, store
        pass

    def query(self, text: str):
        """Retrieve relevant code snippets"""
        # TODO: vector search
        return []