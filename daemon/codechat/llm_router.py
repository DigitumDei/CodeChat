from codechat.models import QueryRequest
from codechat.providers import get as get_provider

class LLMRouter:
    def __init__(self):
        from codechat import providers  # noqa: F401 auto‑import side‑effects

    def route(self, req: QueryRequest) -> dict:
        return get_provider(req.provider.value).send(req)

    async def stream(self, req: QueryRequest):
        async for chunk in await get_provider(req.provider.value).stream(req):
            yield chunk
    
    