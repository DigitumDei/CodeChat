from fastapi import FastAPI
from codechat.indexer import Indexer
from codechat.watcher import Watcher
from codechat.llm_router import LLMRouter
from codechat.models import QueryRequest
from codechat.errors import add_global_error_handlers
from codechat.logging import setup_logging, RequestIDMiddleware
import structlog

app = FastAPI(title="CodeChat Daemon")

# install our unified handlers before anything else
add_global_error_handlers(app)

# ---- structured logging setup ----
# load config early so we can pass it into setup_logging
router = LLMRouter()            # router loads cfg in its ctor
setup_logging(router.cfg)
app.add_middleware(RequestIDMiddleware)

# instantiate core components
indexer = Indexer()
watcher = Watcher(indexer)

# background tasks
@app.on_event("startup")
def startup_tasks():
    # start filesystem watcher
    watcher.start()
    struct_logger = structlog.get_logger("server.startup")
    struct_logger.info("Filesystem watcher started", path=".")

# HTTP endpoints (future REST/gRPC)
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/query")
def handle_query(request: QueryRequest):
    # route to appropriate LLM backend
    return router.route(request)


@app.post("/admin/reload-config")
async def reload_config():
    """
    Triggers the LLMRouter to reload its configuration from the file.
    """
    logger = structlog.get_logger("server.reload_config")
    try:
        logger.info("Reloading configuration...")
        router.set_config() # Call set_config on the existing instance
        logger.info("Configuration reloaded.")
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        logger.error("Error reloading configuration?", exception=str(e))
        return {"status" : "error", "message": str(e)}



def serve(host: str = '127.0.0.1', port: int = 5005):
    import uvicorn
    # disable uvicorn’s own access logs in favor of our structured output
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
    )
