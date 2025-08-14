# daemon/codechat/dep_graph.py
import pathlib
import networkx as nx
import structlog

from tree_sitter import Parser, Language, Query
from tree_sitter_language_pack import get_language  # type: ignore[import-not-found]
from typing import cast, Any

from typing import Callable, Dict, Set, Optional

logger = structlog.get_logger(__name__)

# --- Language Specific Configuration ---

def _extract_python_dep(module_full_name: str) -> str:
    return module_full_name.split(".")[0]

def _extract_js_ts_dep(import_path: str) -> str:
    # 'lodash', './utils/helper.js' -> 'helper', 'package/sub' -> 'package'
    # Strips quotes, then processes.
    path_str = import_path.strip("'\"")
    p = pathlib.Path(path_str)
    if path_str.startswith('.') or path_str.startswith('/'):
        return p.stem
    return p.parts[0] if p.parts else p.stem # Handles 'package' vs 'package/sub'

def _extract_c_cpp_dep(include_path: str) -> str:
    # "my/header.h" -> "header", <stdio.h> -> "stdio"
    # Strips quotes or angle brackets.
    return pathlib.Path(include_path.strip("'\"<>")).stem

def _extract_csharp_dep(namespace: str) -> str:
    # System.Text -> System
    return namespace.split('.')[0]

def _extract_html_css_link_dep(link_path: str) -> str:
    # "styles/main.css" -> "main", "theme.css" -> "theme"
    # Strips quotes.
    return pathlib.Path(link_path.strip("'\"")).stem


LangConfig = Dict[str, Language]
QueryConfig = Dict[str, Query]
ExtractorConfig = Dict[str, Callable[[str], str]]
SuffixToLangMap = Dict[str, str]

LANGUAGES: LangConfig = {}
QUERIES: QueryConfig = {}
EXTRACTORS: ExtractorConfig = {}
SUFFIX_TO_LANG: SuffixToLangMap = {}

LANGUAGE_DEFINITIONS = {
    "python": {
        "suffixes": [".py"],
        "query_str": """
            [
              (import_statement name: (dotted_name) @module)
              (import_statement (aliased_import name: (dotted_name) @module))
              (import_from_statement module_name: (dotted_name) @module)
              (import_from_statement module_name: (relative_import) @module)
            ]
        """,
        "extractor": _extract_python_dep,
        "capture_name": "@module"
    },
    "javascript": {
        "suffixes": [".js", ".jsx", ".mjs", ".cjs"],
        "query_str": """
            [
              (import_statement source: (string) @path)
              (export_statement source: (string) @path)
              (call_expression
                function: (identifier) @_fn (#eq? @_fn "require")
                arguments: (arguments (string) @path)
              )
            ]
        """,
        "extractor": _extract_js_ts_dep,
        "capture_name": "@path"
    },
    "typescript": {
        "suffixes": [".ts", ".tsx"],
        "query_str": """
            [
              (import_statement source: (string) @path)
              (export_statement source: (string) @path)
              (call_expression
                function: (identifier) @_fn (#eq? @_fn "require")
                arguments: (arguments (string) @path)
              )
              ; (comment (_ (_)* @comment_content (#match? @comment_content "^///\\s*<reference\\s+path="))) @reference_directive ; More complex
            ]
        """,
        "extractor": _extract_js_ts_dep,
        "capture_name": "@path"
    },
    "csharp": {
        "suffixes": [".cs"],
        "query_str": "(using_directive (qualified_name) @namespace)",
        "extractor": _extract_csharp_dep,
        "capture_name": "@namespace"
    },
    "cpp": { # C++ can also include .c headers and vice-versa
        "suffixes": [".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"],
        "query_str": """
            (preproc_include path: [
              (string_literal) @path
              (system_lib_string) @path
            ])
        """,
        "extractor": _extract_c_cpp_dep,
        "capture_name": "@path"
    },
    "c": {
        "suffixes": [".c", ".h"],
        "query_str": """
            (preproc_include path: [
              (string_literal) @path
              (system_lib_string) @path
            ])
        """,
        "extractor": _extract_c_cpp_dep,
        "capture_name": "@path"
    },
    "html": {
        "suffixes": [".html", ".htm"],
        "query_str": """
            [
              (element (start_tag (tag_name) @_tag (#eq? @_tag "link") (attribute (attribute_name) @_attr (#eq? @_attr "href") (quoted_attribute_value (attribute_value) @path))))
              (element (start_tag (tag_name) @_tag (#eq? @_tag "script") (attribute (attribute_name) @_attr (#eq? @_attr "src") (quoted_attribute_value (attribute_value) @path))))
            ]
        """,
        "extractor": _extract_html_css_link_dep,
        "capture_name": "@path"
    },
    "css": {
        "suffixes": [".css"],
        "query_str": """
            [
              (import_statement (string_value) @path)
              (import_statement (call_expression (arguments (string_value) @path)))
            ]
        """,
        "extractor": _extract_html_css_link_dep,
        "capture_name": "@path"
    }
}

def _initialize_language_configs():
    for lang_name, config in LANGUAGE_DEFINITIONS.items():
        try:
            # get_language() requires the language name as argument
            # Cast to Any to avoid type checker issues with dynamic strings
            lang_obj = get_language(cast(Any, lang_name))
            LANGUAGES[lang_name] = lang_obj
            
            # The Query constructor issue - try both patterns
            try:
                # Try language.query(string) first (most likely correct)
                query_obj = lang_obj.query(config["query_str"])
            except AttributeError:
                # Fallback to Query(language, string) if lang_obj doesn't have query method
                query_obj = Query(lang_obj, config["query_str"])
            
            QUERIES[lang_name] = query_obj
            EXTRACTORS[lang_name] = config["extractor"]
            for suffix in config["suffixes"]:
                SUFFIX_TO_LANG[suffix] = lang_name
                
            logger.info("Successfully initialized language config", language=lang_name)
            
        except Exception as e:
            logger.error("Failed to initialize language config", language=lang_name, error=str(e), exc_info=True)

_initialize_language_configs()

class DepGraph:
    """Builds a directed graph of local file dependencies where edges represent import relationships."""
    def __init__(self, project_root: Optional[pathlib.Path] = None):
        self.graph: nx.DiGraph = nx.DiGraph()
        self.parser = Parser()
        self.project_root = project_root
        self.file_map: Dict[str, pathlib.Path] = {}  # Maps project-relative paths to full paths
        self.import_cache: Dict[str, Set[pathlib.Path]] = {}  # Cache for import resolution

    def build(self, files: list[pathlib.Path]) -> None:
        """Build a dependency graph of local file relationships."""
        self.graph.clear()
        self.file_map.clear()
        self.import_cache.clear()
        
        # Infer project root if not provided
        if self.project_root is None and files:
            self.project_root = self._infer_project_root(files)
            
            # Warn about potentially problematic project roots
            if str(self.project_root) in ['/', '/home', '/usr', '/var']:
                logger.warning("Project root inferred as system directory, file IDs may be very long", 
                             project_root=str(self.project_root),
                             sample_file_ids=[self._get_file_id(f) for f in files[:3]])
            elif len(self.project_root.parts) <= 2:
                logger.info("Project root is quite shallow, file IDs will include full directory structure", 
                          project_root=str(self.project_root),
                          sample_file_ids=[self._get_file_id(f) for f in files[:3]])
        
        # Build file mapping: project-relative path -> full path
        for path in files:
            try:
                if self.project_root is not None:
                    rel_path = path.relative_to(self.project_root)
                    file_id = str(rel_path)
                else:
                    file_id = str(path)
                self.file_map[file_id] = path
                self.graph.add_node(file_id)
            except ValueError:
                # File is outside project root, use absolute path as fallback
                file_id = str(path)
                self.file_map[file_id] = path
                self.graph.add_node(file_id)
        
        logger.debug("File map built", 
                    total_files=len(self.file_map),
                    sample_paths=list(self.file_map.keys())[:5])
        
        # Build file-to-file dependencies
        for path in files:
            try:
                if self.project_root is not None:
                    rel_path = path.relative_to(self.project_root)
                    file_id = str(rel_path)
                else:
                    file_id = str(path)
            except ValueError:
                file_id = str(path)
                
            logger.debug("Processing file for dependencies", file=str(path), file_id=file_id)
            
            local_dependencies = self._resolve_local_imports(path)
            logger.debug("Found local dependencies", file_id=file_id, dependencies=[self._get_file_id(d) for d in local_dependencies])
            
            for dep_path in local_dependencies:
                dep_id = self._get_file_id(dep_path)
                if dep_id in self.file_map:  # Only add edges for files in our project
                    self.graph.add_edge(file_id, dep_id)
                    logger.debug("Added edge", from_file=file_id, to_file=dep_id)
                else:
                    logger.debug("Skipped dependency (not in file_map)", dep=dep_id)
                    
        logger.info("Local dependency graph built.", 
                   nodes=self.graph.number_of_nodes(), 
                   edges=self.graph.number_of_edges(),
                   project_root=str(self.project_root))

    # ---------- helpers -------------------------------------------------
    def _get_file_id(self, path: pathlib.Path) -> str:
        """Get stable file identifier - project-relative path or absolute path."""
        try:
            if self.project_root is not None:
                rel_path = path.relative_to(self.project_root)
                return str(rel_path)
            else:
                return str(path)
        except (ValueError, TypeError):
            # File outside project root or no project root
            return str(path)
    
    def _infer_project_root(self, files: list[pathlib.Path]) -> pathlib.Path:
        """Infer project root by finding common parent directory."""
        if not files:
            return pathlib.Path.cwd()
        
        # Find common parent of all files by comparing path parts
        if len(files) == 1:
            return files[0].parent
            
        # Start with first file's parent
        common_parts = list(files[0].parent.parts)
        
        # Find common prefix with all other files
        for file_path in files[1:]:
            file_parts = list(file_path.parent.parts)
            
            # Find common prefix between current common_parts and this file's parts
            new_common_parts = []
            for i in range(min(len(common_parts), len(file_parts))):
                if common_parts[i] == file_parts[i]:
                    new_common_parts.append(common_parts[i])
                else:
                    break
            common_parts = new_common_parts
            
            # If no common parts remain, fall back to root
            if not common_parts:
                return pathlib.Path("/")
        
        # Reconstruct path from common parts
        if common_parts:
            project_root = pathlib.Path(*common_parts)
            logger.debug("Inferred project root from common parts", 
                        project_root=str(project_root),
                        num_files=len(files),
                        sample_files=[str(f) for f in files[:3]])
            return project_root
        else:
            logger.warning("No common path parts found, falling back to filesystem root")
            return pathlib.Path("/")

    def _resolve_local_imports(self, file_path: pathlib.Path) -> Set[pathlib.Path]:
        """Resolve imports in a file to actual local file paths."""
        if not self.project_root:
            return set()
            
        raw_imports = self._parse_raw_imports(file_path)
        local_files: Set[pathlib.Path] = set()
        
        for import_path in raw_imports:
            resolved_paths = self._resolve_import_path(import_path, file_path)
            local_files.update(resolved_paths)
            
        return local_files

    def _parse_raw_imports(self, path: pathlib.Path) -> set[str]:
        """Parse raw import statements without any extraction/filtering."""
        raw_imports: Set[str] = set()
        lang_name = SUFFIX_TO_LANG.get(path.suffix.lower())

        if not lang_name or lang_name not in LANGUAGES:
            logger.debug("No language support for file", file=str(path), suffix=path.suffix)
            return raw_imports
        
        lang_obj = LANGUAGES[lang_name]
        query_obj = QUERIES[lang_name]

        self.parser.language = lang_obj

        try:
            content_bytes = path.read_bytes()
            tree = self.parser.parse(content_bytes)
            captures_dict = query_obj.captures(tree.root_node)

            # Collect raw import strings without any extraction
            for _capture_name, captured_nodes in captures_dict.items():
                for node in captured_nodes:
                    if node.text:
                        raw_text = node.text.decode("utf-8", errors="replace").strip("'\"")
                        if raw_text:
                            raw_imports.add(raw_text)
                            logger.debug("Found raw import", file=str(path), import_text=raw_text)
            
            logger.debug("Raw imports parsed", file=str(path), count=len(raw_imports), imports=list(raw_imports))
                            
        except FileNotFoundError:
            logger.warning("File not found during import parsing.", path=str(path), lang=lang_name)
        except Exception as e:
            logger.error("Error parsing imports.", path=str(path), lang=lang_name, error=str(e), exc_info=True)
        return raw_imports

    def _resolve_import_path(self, import_path: str, from_file: pathlib.Path) -> Set[pathlib.Path]:
        """Resolve an import path to actual local file paths using conservative heuristics."""
        resolved_paths: Set[pathlib.Path] = set()
        
        # Cache key for this resolution
        cache_key = f"{import_path}:{from_file}"
        if cache_key in self.import_cache:
            return self.import_cache[cache_key]
        
        logger.debug("Resolving import", import_path=import_path, from_file=str(from_file))
        
        # Strategy 1: Relative imports (highest confidence)
        if import_path.startswith('.'):
            resolved_paths.update(self._resolve_relative_import(import_path, from_file))
        
        # Strategy 2: Direct file path match in file_map
        # Look for exact matches: "codechat/vector_db" -> "codechat/vector_db.py"
        for file_id in self.file_map:
            file_path = self.file_map[file_id]
            # Don't allow self-imports
            if file_path == from_file:
                continue
            if self._import_matches_file_id(import_path, file_id):
                resolved_paths.add(file_path)
                logger.debug("File path match", import_path=import_path, file_id=file_id)
        
        # Strategy 3: Last component of dotted imports (conservative)
        # "codechat.models" should match "models.py" if there's reasonable context
        if '.' in import_path and not import_path.startswith('.'):
            last_component = import_path.split('.')[-1]
            for file_id in self.file_map:
                file_path = self.file_map[file_id]
                # Don't allow self-imports
                if file_path == from_file:
                    continue
                if pathlib.Path(file_id).stem == last_component:
                    resolved_paths.add(file_path)
                    logger.debug("Last component match", import_path=import_path, 
                               component=last_component, file_id=file_id)
        
        logger.debug("Import resolution complete", 
                    import_path=import_path, 
                    resolved_count=len(resolved_paths),
                    resolved_files=[self._get_file_id(p) for p in resolved_paths])
        
        self.import_cache[cache_key] = resolved_paths
        return resolved_paths
    
    def _import_matches_file_id(self, import_path: str, file_id: str) -> bool:
        """Check if an import path matches a file ID with conservative rules."""
        # Strip file extensions from import path for comparison
        clean_import = import_path.replace('.js', '').replace('.ts', '').replace('.css', '')
        
        # Convert to Path objects for comparison
        file_path = pathlib.Path(file_id)
        
        # For direct imports (no path separators), be conservative about subdirectories
        if '/' not in clean_import and '.' not in clean_import:
            # Simple name match: "utils" should match "utils.py" but not "subdir/utils.py"
            if file_path.stem == clean_import:
                # For simple imports, only match files at root level (no path separators)
                # This prevents over-linking to files in subdirectories
                if '/' not in file_id:  # Root level file
                    return True
                # Don't match subdirectory files for simple imports to prevent over-linking
                return False
            
        # Path-based match: "src/utils" -> "src/utils.py"
        if file_path.with_suffix('') == pathlib.Path(clean_import):
            return True
            
        return False

    def _resolve_relative_import(self, import_path: str, from_file: pathlib.Path) -> Set[pathlib.Path]:
        """Resolve relative imports like ./module, ../other."""
        resolved_paths: Set[pathlib.Path] = set()
        
        # Handle imports that already include file extensions
        clean_path = import_path.lstrip('./')
        if clean_path.endswith(('.js', '.ts', '.py', '.jsx', '.tsx')):
            # Import already has extension, use it directly
            clean_name = clean_path
        else:
            # No extension provided
            clean_name = clean_path
        
        # Count leading dots to determine relative level
        dot_count = len(import_path) - len(import_path.lstrip('.'))
        
        # Start from the file's directory and go up 'dot_count - 1' levels
        start_dir = from_file.parent
        for _ in range(max(0, dot_count - 1)):
            start_dir = start_dir.parent
        
        # Try to find the module file
        if clean_name.endswith(('.js', '.ts', '.py', '.jsx', '.tsx')):
            # Import has extension, try exact match first
            potential_paths = [start_dir / clean_name]
        else:
            # Import has no extension, try various extensions
            potential_paths = [
                start_dir / f"{clean_name}.py",
                start_dir / clean_name / "__init__.py",
                start_dir / f"{clean_name}.ts",
                start_dir / f"{clean_name}.js",
                start_dir / f"{clean_name}.jsx",
                start_dir / f"{clean_name}.tsx",
            ]
        
        for potential_path in potential_paths:
            if potential_path.exists() and potential_path != from_file:
                resolved_paths.add(potential_path)
                logger.debug("Resolved relative import", 
                           import_path=import_path,
                           from_file=str(from_file),
                           resolved_to=str(potential_path))
        
        return resolved_paths

    def _resolve_absolute_import(self, import_path: str) -> Set[pathlib.Path]:
        """Resolve absolute imports within the project."""
        resolved_paths: Set[pathlib.Path] = set()
        
        if not self.project_root:
            return resolved_paths
        
        # Split import path into components
        parts = import_path.split('.')
        
        # Try different combinations to find local modules
        for i in range(len(parts)):
            # Try: codechat.module -> codechat/module.py
            potential_path = self.project_root
            for part in parts[:i+1]:
                potential_path = potential_path / part
            
            # Try various file extensions
            for ext in ['.py', '.ts', '.js', '.tsx', '.jsx']:
                file_path = potential_path.with_suffix(ext)
                if file_path.exists():
                    resolved_paths.add(file_path)
            
            # Try module directory with __init__.py
            init_path = potential_path / "__init__.py"
            if init_path.exists():
                resolved_paths.add(init_path)
        
        return resolved_paths

    def _imports(self, path: pathlib.Path) -> set[str]:
        """Legacy method - now delegates to local resolution."""
        local_deps = self._resolve_local_imports(path)
        return {dep.stem for dep in local_deps}

    # ---------- query methods -------------------------------------------
    def _get_file_identifier_if_valid(self, file_path: pathlib.Path) -> Optional[str]:
        """Helper to get file identifier (project-relative path) if it's in the graph."""
        file_identifier = self._get_file_id(file_path)
        if file_identifier not in self.graph:
            logger.warning("File identifier not found in graph.", 
                         identifier=file_identifier, 
                         path=str(file_path),
                         available_nodes=list(self.graph.nodes())[:10])
            return None

        return file_identifier

    def get_direct_dependencies(self, file_path: pathlib.Path) -> Set[str]:
        """Returns a set of identifiers that the given file directly depends on."""
        file_identifier = self._get_file_identifier_if_valid(file_path)
        if not file_identifier:
            return set()
        return set(self.graph.successors(file_identifier))

    def get_direct_dependents(self, file_path: pathlib.Path) -> Set[str]:
        """Returns a set of identifiers that directly depend on the given file."""
        file_identifier = self._get_file_identifier_if_valid(file_path)
        if not file_identifier:
            return set()
        return set(self.graph.predecessors(file_identifier))

    def get_all_dependencies(self, file_path: pathlib.Path) -> Set[str]:
        """Returns a set of all identifiers that the given file depends on (transitively)."""
        file_identifier = self._get_file_identifier_if_valid(file_path)
        if not file_identifier:
            return set()
        return nx.descendants(self.graph, file_identifier)

    def get_all_dependents(self, file_path: pathlib.Path) -> Set[str]:
        """Returns a set of all identifiers that depend on the given file (transitively)."""
        file_identifier = self._get_file_identifier_if_valid(file_path)
        if not file_identifier:
            return set()
        return nx.ancestors(self.graph, file_identifier)

    # --- Granular Update Methods ---
    def add_or_update_file(self, path: pathlib.Path) -> None:
        """Adds or updates a file's node and dependencies in the graph."""
        file_identifier = self._get_file_id(path)
        old_dependencies = self.get_direct_dependencies(path)  # Existing dependencies

        # Remove old edges before updating
        if file_identifier in self.graph:
            self.graph.remove_edges_from([(file_identifier, dep) for dep in old_dependencies])

        # Add or ensure the file node itself exists
        self.graph.add_node(file_identifier)
        self.file_map[file_identifier] = path

        # Parse new dependencies and add edges to local files
        local_files = self._resolve_local_imports(path)
        new_dependencies = set()
        for dep_path in local_files:
            dep_id = self._get_file_id(dep_path)
            if dep_id in self.file_map:  # Only add edges for files in our project
                self.graph.add_edge(file_identifier, dep_id)
                new_dependencies.add(dep_id)

        if new_dependencies != old_dependencies:
            logger.info("Updated dependencies for file.", file=file_identifier, old=sorted(old_dependencies), new=sorted(new_dependencies))
        else:
            logger.debug("File dependencies unchanged.", file=file_identifier)

    def remove_file(self, path: pathlib.Path) -> None:
        """Removes a file's node and its dependencies from the graph."""
        file_identifier = self._get_file_id(path)
        if file_identifier in self.graph:
            self.graph.remove_node(file_identifier)
            self.file_map.pop(file_identifier, None)
            logger.info("Removed file from dependency graph.", file=file_identifier)
        else:
            logger.debug("File not found in dependency graph for removal.", file=file_identifier)

    def move_file(self, old_path: pathlib.Path, new_path: pathlib.Path) -> None:
        """Moves a file's node in the graph, updating its identifier and dependencies."""
        old_identifier = self._get_file_id(old_path)
        new_identifier = self._get_file_id(new_path)

        if old_identifier not in self.graph:
            logger.warning("Source file not found in dependency graph for move. Treating as add of new file.", old_file=old_identifier, new_file=new_identifier)
            self.add_or_update_file(new_path)  # Treat as new file
            return

        # Update node if needed: if path changes, we treat it as remove + add.
        if old_identifier != new_identifier:
            self.remove_file(old_path) 
            self.add_or_update_file(new_path) # Re-parse for deps at new location
        else:
            self.add_or_update_file(new_path)  # Just update file (content change, same path)
