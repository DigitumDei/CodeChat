# Function Call Support Analysis

## Overview

This document analyzes the requirements and implementation strategy for adding unified function call support to CodeChat across Anthropic Claude, Google Gemini, and OpenAI models.

## Current State

CodeChat currently supports three LLM providers:
- **Anthropic** (`daemon/codechat/providers/anthropic.py`)
- **Google** (`daemon/codechat/providers/google.py`) 
- **OpenAI** (`daemon/codechat/providers/openai.py`)
- **Azure** (`daemon/codechat/providers/azure.py`)

The system routes requests through `LLMRouter` but does not currently support function calling capabilities.

## Provider Function Calling Capabilities

### Anthropic Claude - Tool Use

**Definition Format:**
```json
{
  "name": "get_weather",
  "description": "Get current weather for a location", 
  "input_schema": {
    "type": "object",
    "properties": {
      "location": {"type": "string", "description": "City name"}
    },
    "required": ["location"]
  }
}
```

**Key Features:**
- Tools passed in `tools` parameter
- Response includes `tool_use` content blocks
- Supports parallel tool calls
- Model decides when to use tools
- Different behavior across Opus/Sonnet/Haiku

### Google Gemini - Function Calling

**Definition Format:**
```json
{
  "name": "get_weather",
  "description": "Get current weather for a location",
  "parameters": {
    "type": "object", 
    "properties": {
      "location": {"type": "string", "description": "City name"}
    },
    "required": ["location"]
  }
}
```

**Key Features:**
- Functions passed in `tools` configuration
- Three modes: `AUTO`, `ANY`, `NONE`
- Structured JSON response with function calls
- Python/JavaScript SDK support
- 10-20 tools recommended limit

### OpenAI - Function Calling

**Definition Format:**
```json
{
  "type": "function",
  "function": {
    "name": "get_weather", 
    "description": "Get current weather for a location",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {"type": "string", "description": "City name"}
      },
      "required": ["location"]
    }
  }
}
```

**Key Features:**
- Tools passed in `tools` parameter with `type: "function"`
- `tool_choice` controls function selection (`auto`, `none`, specific function)
- Structured Outputs with `strict: true` (2024+)
- Parallel function calling support
- JSON Schema compliance required

## Requirements

### Functional Requirements

1. **Unified Function Definition API**
   - Single interface for defining functions across all providers
   - Common schema validation
   - Provider-specific translation layer

2. **Function Registration System**
   - Hard coded function registration - controlled by code and not pluginable
   - Leave room in design for future plugins

3. **Execution Environment**
   - Functions must run in docker container
   - Error handling and logging
   - Timeout and resource limits

4. **Response Handling**
   - Parse provider-specific function call responses
   - Execute requested functions
   - Format results for continued conversation

### Non-Functional Requirements

1. **Security**
   - Prevent code injection attacks
   - Function execution within container
   - Input validation and sanitization   

2. **Performance**
   - Minimal latency overhead
   - Efficient function lookup
   - Caching of function metadata

3. **Reliability**
   - Graceful degradation when functions fail
   - Retry mechanisms for transient failures
   - Comprehensive error handling

## Technical Approach

### 1. Unified Function Schema

Design a common function definition format that can be translated to all providers:

```python
@dataclass
class FunctionDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    required: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    permissions: Optional[List[str]] = None
```

### 2. Provider Translation Layer

Each provider adapter translates the unified schema:

```python
class ProviderFunctionAdapter:
    def translate_function_definition(self, func_def: FunctionDefinition) -> Dict[str, Any]:
        """Translate unified function def to provider-specific format"""
        pass
    
    def parse_function_calls(self, response: Any) -> List[FunctionCall]:
        """Extract function calls from provider response"""
        pass
```

### 3. Function Registry

Central registry for managing available functions:

```python
class FunctionRegistry:
    def register_function(self, func_def: FunctionDefinition, 
                         handler: Callable) -> None:
        """Register a function with its handler"""
        pass
    
    def get_available_functions(self, user_context: UserContext) -> List[FunctionDefinition]:
        """Get functions available to user"""
        pass
```

### 4. Execution Engine

Secure execution environment for function calls:

```python
class FunctionExecutor:
    def execute_function(self, call: FunctionCall, 
                        context: ExecutionContext) -> FunctionResult:
        """Safely execute a function call"""
        pass
```

### 5. Integration Points

#### A. LLM Router Enhancement
```python
class LLMRouter:
    def __init__(self):
        self.function_registry = FunctionRegistry()
        self.function_executor = FunctionExecutor()
    
    async def process_request_with_functions(self, request: QueryRequest) -> StreamingResponse:
        # Include available functions in provider request
        # Handle function call responses
        # Execute functions and continue conversation
        pass
```

#### B. Provider Integration
Each provider (`anthropic.py`, `openai.py`, etc.) gets function call support:

```python
class AnthropicProvider:
    def prepare_request_with_functions(self, request: QueryRequest, 
                                     functions: List[FunctionDefinition]) -> Dict[str, Any]:
        """Add Anthropic-formatted tools to request"""
        pass
    
    def extract_function_calls(self, response: Dict[str, Any]) -> List[FunctionCall]:
        """Parse Anthropic tool_use blocks"""
        pass
```

## Implementation Plan

### Phase 1: Foundation
1. **Core Data Models**
   - Define `FunctionDefinition`, `FunctionCall`, `FunctionResult` models
   - Create base provider adapter interface
   - Implement function registry

2. **Provider Adapters**
   - Implement Anthropic adapter (tool use format)
   - Implement OpenAI adapter (function calling format)
   - Implement Google adapter (function calling format)

### Phase 2: Execution Engine
1. **Function Executor**
   - Secure execution sandbox
   - Input validation and sanitization
   - Error handling and logging

2. **Built-in Functions**
   - File operations (read, write, list)
   - Code execution (Python, shell commands)
   - Web requests (HTTP GET/POST)
   - System information queries

### Phase 3: Integration
1. **LLM Router Enhancement**
   - Integrate function registry with request processing
   - Handle function call responses
   - Implement conversation flow with function results

2. **Provider Updates**
   - Update all provider classes with function call support
   - Add provider-specific configuration options
   - Test function calling with each provider

### Phase 4: Security & Configuration
1. **Security Hardening**
   - Implement execution sandboxing
   - Add permission system
   - Security audit and testing

2. **Configuration System**
   - Function availability configuration
   - Per-user permissions
   - Provider-specific function call settings

### Phase 5: Testing & Documentation
1. **Comprehensive Testing**
   - Unit tests for all components
   - Integration tests with real providers
   - Security testing

2. **Documentation**
   - API documentation
   - Function development guide
   - Configuration examples

## Considerations

### Security Concerns
- **Code Injection**: Validate all function inputs
- **File System Access**: Restrict file operations to safe directories
- **Network Access**: Control outbound requests
- **Resource Limits**: Prevent resource exhaustion attacks

### Performance Implications
- **Function Discovery**: Cache function metadata for performance
- **Execution Overhead**: Minimize latency from function calls
- **Memory Usage**: Limit memory consumption of executed functions

### Provider Differences
- **Response Formats**: Handle varying function call response structures
- **Capabilities**: Some providers may have limitations (parallel calls, parameter types)
- **Rate Limits**: Consider provider-specific rate limiting

### Error Handling Strategy
- **Function Failures**: Graceful degradation when functions fail
- **Provider Errors**: Handle provider-specific error responses
- **Network Issues**: Retry mechanisms for transient failures

### Configuration Complexity
- **Per-Provider Settings**: Different configuration needs per provider
- **User Permissions**: Fine-grained access control
- **Function Availability**: Dynamic function enabling/disabling

## References

- [Anthropic Tool Use Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview)
- [Google Gemini Function Calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [CodeChat LLM Router Implementation](../daemon/codechat/llm_router.py)
- [CodeChat Provider Implementations](../daemon/codechat/providers/)