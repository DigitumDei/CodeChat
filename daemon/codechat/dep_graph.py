# daemon/codechat/dep_graph.py
import pathlib
import networkx as nx
import structlog

from tree_sitter import Parser, Language, Query, Node
from tree_sitter_languages import get_language

from typing import Callable, Dict, Set, Optional, cast

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
            (import_statement name: (dotted_name) @module)
            (import_from_statement module_name: (dotted_name) @module)
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
    "c_sharp": {
        "suffixes": [".cs"],
        "query_str": "(using_directive name: (qualified_name) @namespace)",
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
            (import_statement [ (string_literal) @path (call_expression function: (identifier) @_fn (#eq? @_fn "url") arguments: (arguments (string_literal) @path))])
        """,
        "extractor": _extract_html_css_link_dep,
        "capture_name": "@path"
    }
}

def _initialize_language_configs():
    for lang_name, config in LANGUAGE_DEFINITIONS.items():
        try:
            lang_obj = get_language(lang_name)
            LANGUAGES[lang_name] = lang_obj
            QUERIES[lang_name] = lang_obj.query(config["query_str"])
            EXTRACTORS[lang_name] = config["extractor"]
            for suffix in config["suffixes"]:
                SUFFIX_TO_LANG[suffix] = lang_name
        except Exception as e:
            logger.error("Failed to initialize language config", language=lang_name, error=str(e))

_initialize_language_configs()

class DepGraph:
    """Builds a directed graph of `file_identifier -> dependency_identifier` edges."""
    def __init__(self):
        self.graph = nx.DiGraph()
        self.parser = Parser()

    def build(self, files: list[pathlib.Path]) -> None:
        self.graph.clear()
        for path in files:
            file_identifier = path.stem  # Node identifier based on file stem
            self.graph.add_node(file_identifier) # Add node even if no imports found/parsed
            imports = self._imports(path)
            for dep_identifier in imports:
                self.graph.add_edge(file_identifier, dep_identifier)
        logger.info("Dependency graph built.", nodes=self.graph.number_of_nodes(), edges=self.graph.number_of_edges())

    # ---------- helpers -------------------------------------------------
    def _imports(self, path: pathlib.Path) -> set[str]:
        deps: Set[str] = set()
        lang_name = SUFFIX_TO_LANG.get(path.suffix.lower())

        if not lang_name or lang_name not in LANGUAGES:
            return deps
        
        lang_obj = LANGUAGES[lang_name]
        query_obj = QUERIES[lang_name]
        extractor_fn = EXTRACTORS[lang_name]

        self.parser.language = Language(lang_obj)

        try:
            content_bytes = path.read_bytes()
            tree = self.parser.parse(content_bytes)
            captures_dict = query_obj.captures(tree.root_node)

            # Per the type hint, captures() returns a dict: {capture_name: [nodes...]}
            # We iterate through all key-value pairs and process all nodes found.
            for _capture_name, captured_nodes in captures_dict.items():
                for node in captured_nodes:
                    if node.text:
                        raw_text = node.text.decode("utf-8", errors="replace")
                        dep_identifier = extractor_fn(raw_text)
                        if dep_identifier:
                            deps.add(dep_identifier)
        except FileNotFoundError:
            logger.warning("File not found during import parsing.", path=str(path), lang=lang_name)
        except Exception as e:
            logger.error("Error parsing imports.", path=str(path), lang=lang_name, error=str(e), exc_info=True)
        return deps

    # ---------- query methods -------------------------------------------
    def _get_file_identifier_if_valid(self, file_path: pathlib.Path) -> Optional[str]:
        """Helper to get file identifier (stem) if it's in the graph."""
        file_identifier = file_path.stem
        if file_identifier not in self.graph:
            logger.debug("File identifier not found in graph.", identifier=file_identifier, path=str(file_path))
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
        file_identifier = path.stem
        old_dependencies = self.get_direct_dependencies(path)  # Existing dependencies

        # Remove old edges before updating
        if file_identifier in self.graph:
            self.graph.remove_edges_from([(file_identifier, dep) for dep in old_dependencies])

        # Add or ensure the file node itself exists
        self.graph.add_node(file_identifier)

        # Parse new dependencies and add them as edges
        new_dependencies = self._imports(path)  
        for dep_identifier in new_dependencies:
            self.graph.add_edge(file_identifier, dep_identifier)

        if new_dependencies != old_dependencies:
            logger.info("Updated dependencies for file.", file=file_identifier, old=sorted(old_dependencies), new=sorted(new_dependencies))
        else:
            logger.debug("File dependencies unchanged.", file=file_identifier)

    def remove_file(self, path: pathlib.Path) -> None:
        """Removes a file's node and its dependencies from the graph."""
        file_identifier = path.stem
        if file_identifier in self.graph:
            self.graph.remove_node(file_identifier)
            logger.info("Removed file from dependency graph.", file=file_identifier)
        else:
            logger.debug("File not found in dependency graph for removal.", file=file_identifier)

    def move_file(self, old_path: pathlib.Path, new_path: pathlib.Path) -> None:
        """Moves a file's node in the graph, updating its identifier and dependencies."""
        old_identifier = old_path.stem
        new_identifier = new_path.stem

        if old_identifier not in self.graph:
            logger.warning("Source file not found in dependency graph for move. Treating as add of new file.", old_file=old_identifier, new_file=new_identifier)
            self.add_or_update_file(new_path)  # Treat as new file
            return

        # Update node if needed: if stem changes, we treat it as remove + add.
        if old_identifier != new_identifier:
            self.remove_file(old_path) 
            self.add_or_update_file(new_path) # Re-parse for deps at new location
        else:
            self.add_or_update_file(new_path)  # Just update file (content change, same name)
