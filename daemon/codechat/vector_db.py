# daemon/codechat/vector_db.py
import faiss # type: ignore
import numpy as np
from pathlib import Path
import pickle
import structlog

logger = structlog.get_logger(__name__)

class VectorDB:
    """
    Tiny convenience layer around FAISS IndexFlatL2.
    Persists the index + metadata to /config/.cache/codechat/faiss.idx|meta.pkl
    """ # Note: The code uses /config/.cache/codechat
    def __init__(self, dim: int = 1536):
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim)
        self.meta: list[dict] = []          # parallel list ‑‑ maps row → {path, hash}
        self._cache_dir = Path("/config/.cache/codechat")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    # ---------- public --------------------------------------------------
    def add(self, meta: dict, vector: list[float]) -> None:
        # meta is expected to be like: {"path": str, "hash": str_hash}
        vec = np.asarray(vector, dtype="float32").reshape(1, -1)
        self.index.add(vec)
        self.meta.append(meta)

    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        if self.index.ntotal == 0:
            return []
        vec = np.asarray(vector, dtype="float32").reshape(1, -1)
        dists, ids = self.index.search(vec, top_k)
        # Ensure that we only try to access valid indices from self.meta
        results = [self.meta[i] | {"score": float(d)} for i, d in zip(ids[0], dists[0]) if i != -1 and 0 <= i < len(self.meta)]
        return results

    def flush(self) -> None:
        faiss.write_index(self.index, str(self._cache_dir / "faiss.idx"))
        with open(self._cache_dir / "meta.pkl", "wb") as f:
            pickle.dump(self.meta, f)

    # ---------- private -------------------------------------------------
    def _load(self):
        idx_p = self._cache_dir / "faiss.idx"
        meta_p = self._cache_dir / "meta.pkl"
        if idx_p.exists() and meta_p.exists():
            self.index = faiss.read_index(str(idx_p))
            with open(meta_p, "rb") as f:
                loaded_meta = pickle.load(f)
                # Ensure self.dim matches the loaded index if it's not empty
                if self.index.ntotal > 0 and self.index.d != self.dim:
                    logger.warning(f"Loaded index dimension {self.index.d} differs from configured dimension {self.dim}. Re-initializing index.")
                    self.index = faiss.IndexFlatL2(self.dim) # Or handle more gracefully
                    self.meta = [] # Mismatch, so old meta is invalid with new index
                else:
                    self.meta = loaded_meta
