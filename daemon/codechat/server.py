from contextlib import asynccontextmanager
import json
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from codechat.indexer import Indexer
from codechat.watcher import Watcher
from codechat.llm_router import LLMRouter
from codechat.models import QueryRequest, DependencyRequest, DependencyResponse, DependencyType
from codechat.errors import add_global_error_handlers
from codechat.logging import setup_logging, RequestIDMiddleware
import structlog
import uvicorn

from codechat.config import get_config, set_config

# instantiate core components early (needed for logging setup and lifespan)
set_config()
indexer = Indexer()
watcher = Watcher(indexer)
router = LLMRouter(indexer) # router loads cfg in its ctor

# ---- structured logging setup ----
setup_logging(get_config())
struct_logger = structlog.get_logger("server.lifespan") # Logger for lifespan events

# ---- Lifespan context manager ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    struct_logger.info("Starting up...")
    watcher.start()
    yield
    # Code to run on shutdown (if any)
    struct_logger.info("Shutting down...")
    struct_logger.info("Filesystem watcher stopped.")

# Create FastAPI app instance *with* the lifespan manager
app = FastAPI(title="CodeChat Daemon", lifespan=lifespan)

# install our unified handlers *after* app creation
add_global_error_handlers(app)
app.add_middleware(RequestIDMiddleware)

# ---- HTTP endpoints ----
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/query")
async def handle_query(query: QueryRequest, stream: bool = Query(default=False)):
    if stream:
        async def event_stream():
            async for chunk in router.stream(query):
                #convert chunk back to json
                chunkjson = json.loads(chunk)
                if chunkjson.get("token"):
                    yield chunkjson.get("token")

        return StreamingResponse(event_stream(),
                                 media_type="text/event-stream")
    result = router.route(query)
    return result.get("text")


@app.post("/admin/reload-config")
async def reload_config():
    """
    Triggers the LLMRouter to reload its configuration from the file.
    """
    logger = structlog.get_logger("server.reload_config")
    try:
        logger.info("Reloading configuration.")
        set_config() # Call set_config on the existing instance
        logger.info("Configuration reloaded.")
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        logger.error("Error reloading configuration?", exception=str(e))
        # Consider returning a proper HTTP error status code here
        # from fastapi import HTTPException
        # raise HTTPException(status_code=500, detail=f"Error reloading config: {e}")
        # For now, keeping the original return structure:
        return {"status" : "error", "message": str(e)}


@app.post("/dependencies", response_model=DependencyResponse)
async def get_dependencies(request: DependencyRequest):
    """
    Get dependency information for a file based on the dependency graph.
    
    Supports querying for:
    - direct_dependencies: Files this file directly imports
    - direct_dependents: Files that directly import this file  
    - all_dependencies: All files this file depends on (transitively)
    - all_dependents: All files that depend on this file (transitively)
    """
    logger = structlog.get_logger("server.dependencies")
    
    try:
        file_path = Path(request.file_path)
        
        # Handle both file paths and file stems
        if file_path.suffix:
            # It's a file path, validate it exists
            if file_path.is_absolute():
                try:
                    file_path = file_path.relative_to(indexer.root)
                except ValueError:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"File path must be within the project root: {indexer.root}"
                    )
            
            # Convert to absolute path for operations
            full_path = indexer.root / file_path
            
            if not full_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found: {file_path}"
                )
        else:
            # It's a file stem, check if it exists in the dependency graph
            file_stem = str(file_path)
            if file_stem not in indexer.dgraph.graph:
                raise HTTPException(
                    status_code=404,
                    detail=f"File stem '{file_stem}' not found in dependency graph. Available stems: {list(indexer.dgraph.graph.nodes())[:10]}..."
                )
            
            # Create a dummy path for the API - the dep graph methods expect a Path but only use .stem
            full_path = Path(file_stem + ".dummy")
        
        # Query the dependency graph based on the requested type
        if request.dependency_type == DependencyType.DIRECT_DEPENDENCIES:
            dependencies = indexer.dgraph.get_direct_dependencies(full_path)
        elif request.dependency_type == DependencyType.DIRECT_DEPENDENTS:
            dependencies = indexer.dgraph.get_direct_dependents(full_path)
        elif request.dependency_type == DependencyType.ALL_DEPENDENCIES:
            dependencies = indexer.dgraph.get_all_dependencies(full_path)
        elif request.dependency_type == DependencyType.ALL_DEPENDENTS:
            dependencies = indexer.dgraph.get_all_dependents(full_path)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown dependency type: {request.dependency_type}"
            )
        
        logger.info(
            "Dependency query completed",
            file_path=str(file_path),
            dependency_type=request.dependency_type,
            count=len(dependencies)
        )
        
        return DependencyResponse(
            file_path=str(file_path),
            dependency_type=request.dependency_type,
            dependencies=dependencies
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error querying dependencies",
            file_path=request.file_path,
            dependency_type=request.dependency_type,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/debug/depgraph")
async def debug_dependency_graph():
    """
    Debug endpoint to inspect the current state of the dependency graph.
    Returns information about nodes, edges, and sample relationships.
    """
    logger = structlog.get_logger("server.debug_depgraph")
    
    try:
        graph = indexer.dgraph.graph
        
        # Basic graph statistics
        num_nodes = graph.number_of_nodes()
        num_edges = graph.number_of_edges()
        
        # Sample nodes (up to 10)
        sample_nodes = list(graph.nodes())[:10] if graph.nodes() else []
        
        # Sample edges (up to 10) 
        sample_edges = list(graph.edges())[:10] if graph.edges() else []
        
        # Find a node with dependencies for example
        example_deps = {}
        if sample_nodes:
            example_node = sample_nodes[0]
            example_deps = {
                "node": example_node,
                "successors": list(graph.successors(example_node)),
                "predecessors": list(graph.predecessors(example_node))
            }
        
        result = {
            "graph_stats": {
                "nodes": num_nodes,
                "edges": num_edges
            },
            "sample_nodes": sample_nodes,
            "sample_edges": sample_edges,
            "example_relationships": example_deps,
            "indexer_root": str(indexer.root)
        }
        
        logger.info("Debug dependency graph query completed", stats=result["graph_stats"])
        
        return result
        
    except Exception as e:
        logger.error("Error in debug dependency graph endpoint", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Debug error: {str(e)}")


# ---- Server execution ----
def serve(host: str = '127.0.0.1', port: int = 16005): # Corrected default port
    # disable uvicorn’s own access logs in favor of our structured output
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None, # Keep this to prevent uvicorn's default logging setup
        access_log=False,
    )

# Optional: If you run this file directly (e.g., python codechat/server.py)
# if __name__ == "__main__":
#     serve()
