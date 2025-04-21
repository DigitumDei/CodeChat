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


def serve(host: str = '127.0.0.1', port: int = 5005):
    import uvicorn
    uvicorn.run(app, host=host, port=port)