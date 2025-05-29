# --- Start of test file (e.g., test_prompt.py) ---
import pytest
from google.genai import types as genai_types
from codechat.models import ChatMessage, QueryRequest, ProviderType, Context, Snippet, SnippetType
from codechat.prompt import PromptManager

# Fixtures
@pytest.fixture
def default_manager():
    return PromptManager()

@pytest.fixture
def custom_manager():
    return PromptManager(system_prompt="Test System Prompt")

@pytest.fixture
def sample_history():
    return [
        ChatMessage(role="user", content="Previous question"),
        ChatMessage(role="assistant", content="Previous answer"),
    ]

@pytest.fixture
def sample_instruction():
    return "Current question"


def sample_query_request(sample_history, sample_instruction, provider=ProviderType.OPENAI) -> QueryRequest:
    return QueryRequest(
        provider=provider,
        model="gpt-test",
        history=sample_history,
        message=sample_instruction,
        # context can be default or you can add snippets for specific tests
        context=Context(snippets=[
            Snippet(type=SnippetType.FILE, content="File content 1"),
            Snippet(type=SnippetType.METHOD, content="Method content 2")
        ])
    )



# Tests
def test_init_default_prompt(default_manager):
    assert default_manager.system_prompt == "You are CodeChat, a helpful assistant for working with code."
    assert default_manager.get_system_prompt() == "You are CodeChat, a helpful assistant for working with code."

def test_init_custom_prompt(custom_manager):
    assert custom_manager.system_prompt == "Test System Prompt"
    assert custom_manager.get_system_prompt() == "Test System Prompt"

def test_format_openai(default_manager, sample_history, sample_instruction):
    expected = [
        {"role": "developer", "content": default_manager.system_prompt},
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
        {"role": "assistant", "content": "file\nFile content 1"},
        {"role": "assistant", "content": "method\nMethod content 2"},
        {"role": "user", "content": "Current question"},
    ]
    assert default_manager._format_openai(sample_query_request(sample_history, sample_instruction)) == expected

def test_format_openai_no_history(default_manager, sample_instruction):
    expected = [
        {"role": "developer", "content": default_manager.system_prompt},
        {"role": "assistant", "content": "file\nFile content 1"},
        {"role": "assistant", "content": "method\nMethod content 2"},
        {"role": "user", "content": "Current question"},
    ]
    assert default_manager._format_openai(sample_query_request([], sample_instruction)) == expected

def test_format_anthropic(default_manager, sample_history, sample_instruction):
    # Anthropic format usually doesn't include the system prompt directly in messages
    expected = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},        
        {"role": "assistant", "content": "file\nFile content 1"},
        {"role": "assistant", "content": "method\nMethod content 2"},
        {"role": "user", "content": "Current question"},
    ]
    # Note: The system prompt might be passed separately to the Anthropic client
    assert default_manager._format_anthropic(sample_query_request(sample_history, sample_instruction)) == expected

def test_format_anthropic_no_history(default_manager, sample_instruction):
    expected = [        
        {"role": "assistant", "content": "file\nFile content 1"},
        {"role": "assistant", "content": "method\nMethod content 2"},
        {"role": "user", "content": "Current question"},
    ]
    assert default_manager._format_anthropic(sample_query_request([], sample_instruction)) == expected

def test_format_google(default_manager, sample_history, sample_instruction):
    # Google format uses specific types and maps 'assistant' to 'model'
    # It typically doesn't include the system prompt within the main message list
    result = default_manager._format_google(sample_query_request(sample_history, sample_instruction))
    assert isinstance(result, list)
    assert len(result) == 2 # history (no instruction) but two contexts
    assert all(isinstance(item, genai_types.Content) for item in result)
    assert result[0].role == "user"
    assert result[0].parts[0].text == "Previous question"
    assert result[1].role == "model" # Note the role change
    assert result[1].parts[0].text == "Previous answer"

def test_format_google_no_history(default_manager, sample_instruction):
    result = default_manager._format_google(sample_query_request([], sample_instruction))
    assert isinstance(result, list)
    assert len(result) == 0

def test_format_azure(default_manager, sample_history, sample_instruction):
    # Azure should behave like OpenAI
    expected = [
        {"role": "developer", "content": default_manager.system_prompt},
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},        
        {"role": "assistant", "content": "file\nFile content 1"},
        {"role": "assistant", "content": "method\nMethod content 2"},
        {"role": "user", "content": "Current question"},
    ]
    assert default_manager._format_azure(sample_query_request(sample_history, sample_instruction)) == expected

def test_format_azure_custom_prompt(custom_manager, sample_history, sample_instruction):
    expected = [
        {"role": "developer", "content": custom_manager.system_prompt},
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
        {"role": "assistant", "content": "file\nFile content 1"},
        {"role": "assistant", "content": "method\nMethod content 2"},
        {"role": "user", "content": "Current question"},
    ]
    assert custom_manager._format_azure(sample_query_request(sample_history, sample_instruction)) == expected

# --- End of test file ---
