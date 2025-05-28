from enum import Enum
from typing import List, Literal 
from pydantic import BaseModel, Field

class ProviderType(str, Enum):
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE    = "google"
    AZURE     = "azure"

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(
        ..., description="The role of this message in the conversation"
    )
    content: str = Field(..., description="The text content of the message")

class SnippetType(str, Enum):
    FILE = "file"
    SNIPPET = "method"
    SELECTION = "selection"
    DEP_GRAPH = "dep_graph"

class Snippet(BaseModel):
    type: SnippetType = Field(
        ..., description="The type of snippet (e.g., file, code block)"
    )
    content: str = Field(..., description="The content of the snippet")

class Context(BaseModel):
    snippets: List[Snippet] = Field(
        default_factory=list,
        description="List of relevant code snippets or files"
    )


class QueryRequest(BaseModel):
    provider: ProviderType = Field(
        ..., description="Which LLM backend to use"
    )
    model: str = Field(..., description="The model name (e.g. gpt-4, claude-v1)")
    history: List[ChatMessage] = Field(
        default_factory=list,
        description="List of prior messages exchanged"
    )
    message: str = Field(..., description="The new user message to send")
    context: Context

