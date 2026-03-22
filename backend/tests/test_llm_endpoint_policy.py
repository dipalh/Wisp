from pathlib import Path
import re


RUNTIME_FILES = [
    Path(__file__).resolve().parents[1] / "ai" / "client.py",
    Path(__file__).resolve().parents[1] / "ai" / "generate.py",
    Path(__file__).resolve().parents[1] / "ai" / "embed.py",
    Path(__file__).resolve().parents[1] / "main.cjs",
]

BANNED_ENDPOINT_PATTERNS = [
    r"generativelanguage\.googleapis\.com",
    r"api\.openai\.com",
    r"api\.anthropic\.com",
]


def test_runtime_llm_endpoints_are_local_only() -> None:
    violations: list[str] = []
    for file_path in RUNTIME_FILES:
        text = file_path.read_text(encoding="utf-8")
        for pattern in BANNED_ENDPOINT_PATTERNS:
            if re.search(pattern, text):
                violations.append(f"{file_path}: pattern '{pattern}'")
    assert not violations, "Found forbidden external LLM endpoint references:\n" + "\n".join(violations)


def test_runtime_code_references_local_ollama_endpoint() -> None:
    content = (Path(__file__).resolve().parents[1] / "main.cjs").read_text(encoding="utf-8")
    assert "http://localhost:11434" in content
