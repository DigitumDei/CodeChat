from fastapi import FastAPI
from codechat.indexer import Indexer
from codechat.watcher import Watcher
from codechat.llm_router import LLMRouter
from codechat.models import QueryRequest

app = FastAPI(title="CodeChat Daemon")

# instantiate core components
indexer = Indexer()
watcher = Watcher(indexer)
router = LLMRouter()

# background tasks
@app.on_event("startup")
def startup_tasks():
    # start filesystem watcher
    watcher.start()

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
    try:
        print("Reloading configuration...")
        router.set_config() # Call set_config on the existing instance
        print("Configuration reloaded.")
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        print(f"Error reloading configuration: {e}")
        return {"status" : "error", "message": str(e)}



def serve(host: str = '127.0.0.1', port: int = 5005):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
