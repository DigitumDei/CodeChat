# daemon/codechat/vector_db.py
import faiss # type: ignore
import numpy as np
from pathlib import Path
import pickle
import structlog
from typing import Optional, List, Dict, Any # For type hinting

logger = structlog.get_logger(__name__)

class VectorDB:
    def __init__(self, dim: int = 1536):
        self.dim = dim
        # Use IndexIDMap to allow assigning custom IDs and removing them
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dim))
        self.meta_data: Dict[int, Dict[str, Any]] = {} # Maps FAISS ID to meta dict {"path": str, "hash": str}
        self._path_to_faiss_id: Dict[str, int] = {}   # Maps path to FAISS ID
        self._next_faiss_id: int = 0                  # Counter for unique FAISS IDs

        self._cache_dir = Path("/config/.cache/codechat")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self._validate_and_cleanup_stale_mappings()

    def _get_next_faiss_id(self) -> int:
        current_id = self._next_faiss_id
        self._next_faiss_id += 1
        return current_id

    def _validate_and_cleanup_stale_mappings(self) -> None:
        """Remove stale mappings where FAISS IDs are out of range."""
        stale_paths = []
        stale_faiss_ids = []
        
        # Check for FAISS IDs that are out of range
        for path_str, faiss_id in self._path_to_faiss_id.items():
            if faiss_id >= self.index.ntotal:
                stale_paths.append(path_str)
                stale_faiss_ids.append(faiss_id)
        
        # Clean up stale mappings
        for path_str in stale_paths:
            del self._path_to_faiss_id[path_str]
            
        for faiss_id in stale_faiss_ids:
            if faiss_id in self.meta_data:
                del self.meta_data[faiss_id]
        
        if stale_paths:
            logger.info("Cleaned up stale FAISS mappings", count=len(stale_paths), 
                       total_index_size=self.index.ntotal)

    # ---------- public --------------------------------------------------
    def add(self, path_str: str, file_hash: str, vector: List[float]) -> None:
        if path_str in self._path_to_faiss_id:
            logger.warning("Path already exists in VectorDB. Removing old entry before adding.", path=path_str)
            self.remove_by_path(path_str) # Ensure no duplicates by path

        faiss_id = self._get_next_faiss_id()
        meta = {"path": path_str, "hash": file_hash} # Store original path and hash

        vec_np = np.asarray(vector, dtype="float32").reshape(1, -1)
        ids_np = np.array([faiss_id], dtype='int64')

        self.index.add_with_ids(vec_np, ids_np)
        self.meta_data[faiss_id] = meta
        self._path_to_faiss_id[path_str] = faiss_id
        logger.debug("Added to VectorDB", path=path_str, faiss_id=faiss_id, hash=file_hash)


    def remove_by_path(self, path_str: str) -> bool:
        faiss_id = self._path_to_faiss_id.get(path_str)
        if faiss_id is not None:
            try:
                self.index.remove_ids(np.array([faiss_id], dtype='int64'))
                del self.meta_data[faiss_id]
                del self._path_to_faiss_id[path_str]
                logger.debug("Removed from VectorDB", path=path_str, faiss_id=faiss_id)
                return True
            except Exception as e: # faiss can throw RuntimeError if ID not found in index but was in maps
                logger.error("Error removing from FAISS index or metadata", path=path_str, faiss_id=faiss_id, error=e)
                # Clean up potentially inconsistent state if possible
                if faiss_id in self.meta_data: 
                    del self.meta_data[faiss_id]
                if path_str in self._path_to_faiss_id: 
                    del self._path_to_faiss_id[path_str]
        else:
            logger.debug("Path not found in VectorDB for removal", path=path_str)
        return False

    def get_meta_by_path(self, path_str: str) -> Optional[Dict[str, Any]]:
        faiss_id = self._path_to_faiss_id.get(path_str)
        if faiss_id is not None:
            return self.meta_data.get(faiss_id)
        return None

    def search(self, vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        if self.index.ntotal == 0:
            return []
        vec_np = np.asarray(vector, dtype="float32").reshape(1, -1)
        distances, faiss_ids = self.index.search(vec_np, top_k) # faiss_ids are our custom IDs

        results = []
        for i in range(len(faiss_ids[0])):
            faiss_id = faiss_ids[0][i]
            dist = distances[0][i]
            if faiss_id != -1: # FAISS uses -1 for no result / padding
                meta = self.meta_data.get(faiss_id)
                if meta:
                    results.append({**meta, "score": float(dist)})
        return results

    def flush(self) -> None:
        # Persist FAISS index
        faiss.write_index(self.index, str(self._cache_dir / "faiss.idx"))

        # Persist metadata and next_faiss_id
        persistence_data = {
            "meta_data": self.meta_data,
            "_path_to_faiss_id": self._path_to_faiss_id,
            "_next_faiss_id": self._next_faiss_id
        }
        with open(self._cache_dir / "meta_plus.pkl", "wb") as f: # New filename
            pickle.dump(persistence_data, f)
        logger.info("VectorDB flushed to disk.", index_size=self.index.ntotal, meta_count=len(self.meta_data))

    # ---------- private -------------------------------------------------
    def _load(self):
        idx_p = self._cache_dir / "faiss.idx"
        meta_plus_p = self._cache_dir / "meta_plus.pkl" # New filename

        if idx_p.exists() and meta_plus_p.exists():
            try:
                self.index = faiss.read_index(str(idx_p))
                # Ensure the loaded index is an IndexIDMap and its sub-index has the correct dimension
                if not isinstance(self.index, faiss.IndexIDMap) or self.index.index.d != self.dim:
                    logger.warning(f"Loaded index type/dimension mismatch. Expected IndexIDMap with dim {self.dim}, got {type(self.index)} with dim {getattr(self.index.index, 'd', 'N/A')}. Re-initializing.")
                    self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dim))
                    self.meta_data = {}
                    self._path_to_faiss_id = {}
                    self._next_faiss_id = 0
                    return

                with open(meta_plus_p, "rb") as f:
                    persistence_data = pickle.load(f)
                    self.meta_data = persistence_data.get("meta_data", {})
                    self._path_to_faiss_id = persistence_data.get("_path_to_faiss_id", {})
                    self._next_faiss_id = persistence_data.get("_next_faiss_id", 0)
                logger.info("VectorDB loaded from disk.", index_size=self.index.ntotal, meta_count=len(self.meta_data), next_id=self._next_faiss_id)

            except Exception as e:
                logger.error("Failed to load VectorDB from disk. Re-initializing.", error=e, exc_info=True)
                self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dim))
                self.meta_data = {}
                self._path_to_faiss_id = {}
                self._next_faiss_id = 0
        else:
            logger.info("No existing VectorDB found on disk. Initializing new one.")
            # Ensure index is of the correct type even if no files found
            self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dim))


    # This method is for the Indexer's full build.
    def get_all_meta_for_rebuild(self) -> Dict[str, Dict[str, Any]]:
        """Returns a copy of path_to_meta for the indexer's full rebuild logic"""
        path_to_full_meta = {}
        for path_str, faiss_id in self._path_to_faiss_id.items():
            meta = self.meta_data.get(faiss_id)
            if meta:
                path_to_full_meta[path_str] = meta.copy()
        return path_to_full_meta

    def get_vector_by_path(self, path_str: str) -> Optional[List[float]]:
        faiss_id = self._path_to_faiss_id.get(path_str)
        if faiss_id is not None and self.index.ntotal > 0:
            # Validate FAISS ID is within valid range before attempting reconstruct
            if faiss_id >= self.index.ntotal:
                logger.debug("FAISS ID out of range, cleaning up stale mapping.", 
                           path=path_str, faiss_id=faiss_id, ntotal=self.index.ntotal)
                # Clean up stale mapping
                if faiss_id in self.meta_data:
                    del self.meta_data[faiss_id]
                if path_str in self._path_to_faiss_id:
                    del self._path_to_faiss_id[path_str]
                return None
                
            try:
                # IndexIDMap.reconstruct takes a single ID
                reconstructed_vector = self.index.index.reconstruct(faiss_id) # Call reconstruct on the underlying index
                if reconstructed_vector is not None and reconstructed_vector.size > 0:
                    return reconstructed_vector.flatten().tolist()
            except RuntimeError as e: 
                logger.warning("FAISS reconstruct failed for path, ID might be stale or removed.", 
                             path=path_str, faiss_id=faiss_id, error=e)
                # Clean up stale mapping on error
                if faiss_id in self.meta_data:
                    del self.meta_data[faiss_id]
                if path_str in self._path_to_faiss_id:
                    del self._path_to_faiss_id[path_str]
        return None
