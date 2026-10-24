"""Unit tests for LLM provider abstraction, code parsing, and mock provider."""

from llm.provider import LLMResponse, MockLLMProvider


def test_extract_python_code_from_markdown():
    markdown = (
        "Here is the solution:\n\n"
        "```python\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "```\n\n"
        "Hope this helps!"
    )
    resp = LLMResponse(content=markdown)
    code = resp.extract_python_code()
    assert code == "def add(a: int, b: int) -> int:\n    return a + b"


def test_extract_python_code_without_markdown():
    raw_code = "def add(a, b):\n    return a + b"
    resp = LLMResponse(content=raw_code)
    assert resp.extract_python_code() == raw_code


def test_mock_llm_provider_scripting():
    mock = MockLLMProvider()
    mock.set_response("factorial", "```python\ndef fact(n): return 1 if n <= 1 else n * fact(n-1)\n```")

    res = mock.generate("Please implement factorial function")
    assert "fact(n)" in res.extract_python_code()
