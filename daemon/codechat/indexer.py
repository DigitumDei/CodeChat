# daemon/codechat/indexer.py
from pathlib import Path
import hashlib
from openai import OpenAI
import tiktoken                       # quick token trimming helper

import git
from git.exc import InvalidGitRepositoryError, NoSuchPathError, GitCommandError
import structlog

from codechat.vector_db import VectorDB
from codechat.dep_graph import DepGraph
from codechat.config import get_config

logger = structlog.get_logger(__name__)

EMBED_MODEL = "text-embedding-3-small"
MAX_CHARS   = 8_000                    # don’t embed giant blobs

class Indexer:
    """Watches project files and builds vector index + dep‑graph."""
    def __init__(self, root: str | Path = "."):
        self.root = Path(root).resolve()
        self.vdb  = VectorDB()
        self.dgraph = DepGraph()
        self._client = OpenAI(api_key=get_config().get("openai.key"))

    # ---------- build ---------------------------------------------------
    def build_index(self) -> None:
        logger.info("Starting project re-indexing", root=str(self.root))

        # Load existing metadata and create a lookup map for paths and their original indices
        # self.vdb is loaded during Indexer.__init__ and contains the previous state
        old_meta_by_path = {item['path']: item for item in self.vdb.meta}
        old_path_to_id = {item['path']: i for i, item in enumerate(self.vdb.meta)}

        # Create a new VectorDB instance to build the updated index
        # This ensures files deleted from the project are removed from the index
        temp_new_vdb = VectorDB(dim=self.vdb.dim) # Use the same dimension as the existing VDB

        project_files: list[Path] = []
        git_used_for_discovery = False

        try:
            repo = git.Repo(self.root, search_parent_directories=True)
            git_root = Path(repo.working_dir)
            
            # Get all files: tracked (cached) and untracked (others) that are not gitignored (exclude_standard)
            # -z uses null terminators for safe parsing of filenames with spaces/special chars.
            # Paths are relative to the git_root.
            repo_files_relative = repo.git.ls_files(cached=True, others=True, exclude_standard=True, z=True).split('\0')
            
            processed_repo_files = []
            for rel_path_str in repo_files_relative:
                if not rel_path_str:  # Handle potential empty string from split if list is empty
                    continue
                abs_path = (git_root / rel_path_str).resolve()
                
                # Ensure the file is within the specified self.root directory
                # and meets our criteria (e.g., .py extension)
                try:
                    if abs_path.is_relative_to(self.root): # Checks if abs_path is under self.root
                        if abs_path.is_file() and abs_path.suffix == '.py':
                            if ".venv" not in str(abs_path): # Additional safeguard
                                processed_repo_files.append(abs_path)
                except ValueError: # Not relative_to self.root
                    continue
            
            project_files = processed_repo_files
            git_used_for_discovery = True
            logger.info("Using Git to discover project files.", count=len(project_files), repo_root=str(git_root))

        except (InvalidGitRepositoryError, NoSuchPathError):
            logger.warning("Project root is not a Git repository or path not found. Falling back to rglob.", project_root=str(self.root))
        except GitCommandError as e:
            logger.error("Git command failed. Falling back to rglob.", project_root=str(self.root), error=str(e))
        except Exception as e: # Catch any other unexpected error from GitPython
            logger.error("Unexpected error during Git file discovery. Falling back to rglob.", project_root=str(self.root), error=str(e))

        if not git_used_for_discovery: # Fallback if GitPython not available or if Git discovery failed
            project_files = [p for p in self.root.rglob("*.py") if ".venv" not in str(p)]
            logger.info("Using rglob to discover project files.", count=len(project_files), reason="Git not used or fallback triggered")

        enc = tiktoken.encoding_for_model(EMBED_MODEL) # noqa: F841

        num_embedded = 0
        num_skipped = 0

        logger.info("Build Index Processing {cnt} files", cnt=len(project_files))

        for file_path in project_files: # Renamed 'file' to 'file_path' for clarity
            path_str = str(file_path)
            try:
                full_text_content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error("Failed to read file", path=path_str, error=e)
                continue

            current_hash = hashlib.sha256(full_text_content.encode('utf-8')).hexdigest()
            text_for_embedding_and_meta = full_text_content[:MAX_CHARS]

            old_meta_item = old_meta_by_path.get(path_str)

            if old_meta_item and old_meta_item.get('hash') == current_hash and self.vdb.index.ntotal > 0:
                logger.debug("File unchanged, reusing existing vector", path=path_str)
                old_id = old_path_to_id[path_str]
                # Ensure old_id is valid for the current self.vdb.index
                if 0 <= old_id < self.vdb.index.ntotal:
                    vector_np = self.vdb.index.reconstruct(old_id).reshape(1, -1)
                    temp_new_vdb.add({"path": path_str, "hash": current_hash}, vector_np.flatten().tolist())
                    num_skipped += 1
                else: # Should not happen if maps are consistent, but as a safeguard
                    logger.warning("Old ID out of bounds, re-embedding", path=path_str, old_id=old_id, index_total=self.vdb.index.ntotal)
                    # Fall through to re-embedding logic
            else:
                logger.debug("File new or changed, creating new embedding", path=path_str)
                embedding_response = self._client.embeddings.create(input=text_for_embedding_and_meta, model=EMBED_MODEL)
                vec = embedding_response.data[0].embedding
                temp_new_vdb.add({"path": path_str, "hash": current_hash}, vec)
                num_embedded += 1

        self.vdb = temp_new_vdb # Replace old VDB with the newly built one
        self.vdb.flush()

        # Rebuild dependency graph
        self.dgraph.build(project_files) # Use the filtered list of project_files
        logger.info("Index build complete",
                    total_docs=len(project_files), # Use the count of actual files processed
                    new_or_changed_docs=num_embedded,
                    unchanged_docs=num_skipped,
                    vector_db_size=self.vdb.index.ntotal,
                    dep_graph_nodes=self.dgraph.graph.number_of_nodes())

    # ---------- runtime -------------------------------------------------
    def query(self, text: str, top_k: int = 5) -> list[dict]:
        vec = self._client.embeddings.create(input=text, model=EMBED_MODEL
                                            ).data[0].embedding
        return self.vdb.search(vec, top_k=top_k)
    