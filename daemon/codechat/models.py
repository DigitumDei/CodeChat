from enum import Enum
from typing import List, Literal, Tuple, TypeAlias 
from pydantic import BaseModel, Field

class ProviderType(str, Enum):
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    GEMINI    = "gemini"
    AZURE     = "azure"

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(
        ..., description="The role of this message in the conversation"
    )
    content: str = Field(..., description="The text content of the message")

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
