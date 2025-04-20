class LLMRouter:
    """Routes queries to appropriate LLM backend or tool runner"""
    def __init__(self):
        # load available backends
        pass

    def route(self, payload: dict):
        # inspect payload and dispatch
        # TODO: choose model, build prompt, call API
        return {"response": "stub"}