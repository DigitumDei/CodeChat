# daemon/codechat/indexer.py
from pathlib import Path
import hashlib
from openai import OpenAI
import tiktoken                       # quick token trimming helper
from typing import Optional, List, Dict, Any # Ensure List, Dict, Any are imported if not already

GIT_PYTHON_AVAILABLE = False
try:
    import git
    from git.exc import InvalidGitRepositoryError, NoSuchPathError, GitCommandError
    GIT_PYTHON_AVAILABLE = True
except ImportError:
    # GitPython library itself is not installed.
    pass # GIT_PYTHON_AVAILABLE remains False
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
        self.repo: Optional[git.Repo] = None

        if GIT_PYTHON_AVAILABLE:
            try:
                self.repo = git.Repo(self.root, search_parent_directories=True)
                logger.info("Git repository detected.", repo_root=str(self.repo.working_dir))
            except InvalidGitRepositoryError:
                logger.info("Project root is not a Git repository. Git-based filtering for single events will not be used.", project_root=str(self.root))
            except NoSuchPathError:
                logger.error("Project root path does not exist for GitPython.", project_root=str(self.root))
            except GitCommandError as e: # This can happen if git executable is not found
                logger.warning("Git command error during Indexer initialization. Git-based filtering may be unavailable.", error=str(e), project_root=str(self.root))
            except Exception as e: # Catch any other unexpected error from GitPython
                logger.error("Unexpected error initializing Git repository. Git-based filtering may be unavailable.", error=str(e), project_root=str(self.root))
        else:
            logger.info("GitPython library not available. Git-based filtering will not be used.")

        self.build_index() # Perform initial full index build

    def _is_relevant_path(self, file_path: Path) -> bool:
        """
        Basic check to see if a file path is relevant for indexing a single event.
        """
        try:
            # Ensure path is within the project root
            # Path.is_relative_to raises ValueError if not relative.
            file_path.relative_to(self.root)
        except ValueError:
            logger.debug("File path not under project root, ignoring.", path=str(file_path), root=str(self.root))
            return False

        # 1. Check if it's a file
        if not file_path.is_file():
            logger.debug("Path is not a file, ignoring for single event processing", path=str(file_path))
            return False

        # 2. Application-specific ignore: its own cache directory
        if self.vdb._cache_dir.is_relative_to(self.root):
            try:
                if file_path.is_relative_to(self.vdb._cache_dir):
                    logger.debug("Path is within VDB cache directory, ignoring.", path=str(file_path))
                    return False
            except ValueError:
                pass # file_path is not in cache_dir, or cache_dir is not under self.root

        # 3. Git-based ignore check (respects .gitignore)
        if self.repo:
            try:
                # file_path is absolute. is_ignored needs path relative to repo root.
                path_relative_to_git_root = file_path.relative_to(self.repo.working_dir)
                if self.repo.is_ignored(path_relative_to_git_root):
                    logger.debug("Path is ignored by Git (.gitignore)", path=str(file_path))
                    return False
                else:
                    # Not ignored by Git, and passed previous checks, so it's relevant
                    logger.debug("Path is relevant (checked by Git)", path=str(file_path))
                    return True 
            except ValueError:
                # This means file_path is not under self.repo.working_dir.
                # This could happen if self.root is a subdir of a git repo, and file_path is outside self.root.
                # Or if file_path is not part of ANY git repo found by search_parent_directories.
                # If it's not in the repo, .gitignore rules from that repo don't apply.
                # So, we fall through to non-Git checks.
                logger.debug("Path not within the discovered Git repo's working directory. Proceeding with non-Git checks.", path=str(file_path), git_repo_root=str(self.repo.working_dir))
            except Exception as e: # Catch other Git errors during is_ignored
                logger.warning("Error checking if path is ignored by Git. Proceeding with non-Git checks.", path=str(file_path), error=e)
                # Fall through to non-Git checks

        # 4. Fallback non-Git ignore check (if self.repo is None or Git check fell through/failed)
        # Common ignored directory names/prefixes
        ignored_dir_components = {".venv", "__pycache__", ".hg", ".svn", "node_modules", "build", "dist", "target"}
        # Note: .git is handled by self.repo.is_ignored if Git is active.
        # If Git is not active, we might still want to ignore .git dirs explicitly if encountered.
        # However, build_index's git ls-files would naturally exclude .git contents.
        # For single events, if not a git repo, an event from .git/ itself is unlikely to be a .py file.
        if any(part in ignored_dir_components for part in file_path.parts):
            logger.debug("Path ignored due to common directory component (non-Git check)", path=str(file_path))
            return False

        logger.debug("Path is relevant for single event processing", path=str(file_path))
        return True

    def process_file_event(self, event_type: str, src_path_str: str, dest_path_str: Optional[str] = None) -> None:
        logger.info("Processing file event", event_type=event_type, src_path=src_path_str, dest_path=dest_path_str)
        src_path = Path(src_path_str)

        if event_type in ("created", "modified"):
            if not self._is_relevant_path(src_path):
                return
            try:
                full_text_content = src_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error("Failed to read file for event processing", path=src_path_str, error=e)
                return

            current_hash = hashlib.sha256(full_text_content.encode('utf-8')).hexdigest()
            text_for_embedding = full_text_content[:MAX_CHARS]
            existing_meta = self.vdb.get_meta_by_path(src_path_str)

            if existing_meta and existing_meta.get('hash') == current_hash:
                logger.debug("File event: content unchanged, no update needed", path=src_path_str)
                return

            logger.info("File event: content changed or new, updating index", path=src_path_str)
            self.vdb.remove_by_path(src_path_str) # Remove old if it exists (handles if not found)
            try:
                embedding_response = self._client.embeddings.create(input=text_for_embedding, model=EMBED_MODEL)
                vec = embedding_response.data[0].embedding
                self.vdb.add(path_str=src_path_str, file_hash=current_hash, vector=vec)
                self.vdb.flush() 
                logger.info("TODO: Granular DepGraph update for created/modified file", path=src_path_str)
            except Exception as e:
                logger.error("Failed to get embedding or add to VDB for file event", path=src_path_str, error=e)

        elif event_type == "deleted":
            # For delete, relevance check is mainly to ensure it's within root.
            # If it was in DB, it should be removed regardless of suffix.
            is_under_root = False
            try: 
                src_path.relative_to(self.root)
                is_under_root = True
            except ValueError: 
                pass
            if not is_under_root: 
                logger.debug("Deleted path not under project root", path=src_path_str)
                return

            logger.info("File event: deleting from index", path=src_path_str)
            if self.vdb.remove_by_path(src_path_str):
                self.vdb.flush()
            logger.info("TODO: Granular DepGraph update for deleted file", path=src_path_str)

        elif event_type == "moved":
            if dest_path_str is None: 
                logger.error("File event 'moved' received without dest_path", src_path=src_path_str)
                return
            logger.info("File event: processing move", src_path=src_path_str, dest_path=dest_path_str)
            # Treat as delete old, create new
            self.process_file_event(event_type="deleted", src_path_str=src_path_str)
            self.process_file_event(event_type="created", src_path_str=dest_path_str) # 'created' will handle relevance of dest

    # ---------- build ---------------------------------------------------
    def build_index(self) -> None: # Full rebuild
        logger.info("Starting project FULL re-indexing", root=str(self.root))

        # Get existing data from current VDB to compare against
        old_vdb_snapshot = self.vdb.get_all_meta_for_rebuild() # path -> {path, hash}

        temp_new_vdb = VectorDB(dim=self.vdb.dim) # Use the same dimension as the existing VDB

        project_files: list[Path] = []
        git_used_for_discovery = False

        if self.repo: # Use the repo instance from __init__ if available
            try:
                git_root = Path(self.repo.working_dir)
                # Get all files: tracked (cached) and untracked (others) that are not gitignored (exclude_standard)
                # -z uses null terminators for safe parsing of filenames with spaces/special chars.
                # Paths are relative to the git_root.
                repo_files_relative = self.repo.git.ls_files(cached=True, others=True, exclude_standard=True, z=True).split('\0')
                
                processed_repo_files = []
                for rel_path_str in repo_files_relative:
                    if not rel_path_str:  # Handle potential empty string from split if list is empty
                        continue
                    abs_path = (git_root / rel_path_str).resolve()
                    
                    # Ensure the file is within the specified self.root directory
                    # and meets our criteria (e.g., .py extension)
                    try:
                        if abs_path.is_relative_to(self.root): # Checks if abs_path is under self.root
                            processed_repo_files.append(abs_path)
                    except ValueError: # Not relative_to self.root
                        continue
                
                project_files = processed_repo_files
                git_used_for_discovery = True
                logger.info("Using Git to discover project files for full build.", count=len(project_files), repo_root=str(git_root))

            except GitCommandError as e: # Errors specific to ls-files
                logger.error("Git command failed during full build file discovery. Falling back to rglob.", project_root=str(self.root), error=str(e))
            except Exception as e: # Catch any other unexpected error from GitPython
                logger.error("Unexpected error during Git file discovery for full build. Falling back to rglob.", project_root=str(self.root), error=str(e))
        
        if not GIT_PYTHON_AVAILABLE and not self.repo: # Log if GitPython itself wasn't even available
             logger.info("GitPython library not available. build_index falling back to rglob.")

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
            text_for_embedding = full_text_content[:MAX_CHARS]

            old_meta_item = old_vdb_snapshot.get(path_str) # Use the snapshot

            if old_meta_item and old_meta_item.get('hash') == current_hash:
                logger.debug("File unchanged, reusing existing vector by fetching from old VDB", path=path_str)
                vector_list = self.vdb.get_vector_by_path(path_str) # Get from current self.vdb
                if vector_list:
                    temp_new_vdb.add(path_str=path_str, file_hash=current_hash, vector=vector_list)
                    num_skipped += 1
                else: # Should not happen if maps are consistent, but as a safeguard
                    logger.warning("Could not retrieve vector for unchanged file from old VDB, re-embedding.", path=path_str)
                    embedding_response = self._client.embeddings.create(input=text_for_embedding, model=EMBED_MODEL)
                    vec = embedding_response.data[0].embedding
                    temp_new_vdb.add(path_str=path_str, file_hash=current_hash, vector=vec)
                    num_embedded += 1
            else:
                logger.debug("File new or changed, creating new embedding", path=path_str)
                embedding_response = self._client.embeddings.create(input=text_for_embedding, model=EMBED_MODEL)
                vec = embedding_response.data[0].embedding
                temp_new_vdb.add(path_str=path_str, file_hash=current_hash, vector=vec)
                num_embedded += 1

        self.vdb = temp_new_vdb # Replace old VDB with the newly built one
        self.vdb.flush()

        # Rebuild dependency graph
        self.dgraph.build(project_files) # Still full rebuild for now
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
    