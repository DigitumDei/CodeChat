from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from codechat.indexer import Indexer
from codechat.watcher import Watcher
from codechat.llm_router import LLMRouter
from codechat.models import QueryRequest
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
        logger.info("Reloading configuration...")
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
