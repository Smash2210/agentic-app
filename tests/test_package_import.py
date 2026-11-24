import subprocess
import sys

import pytest

import agentic_app
import agentic_app.llm


def modules_loaded_after(statement: str) -> set[str]:
    """Run `statement` in a fresh interpreter and report which watched modules it loaded."""
    code = (
        f"{statement}\n"
        "import sys\n"
        "print(','.join(m for m in ('agentic_app.llm', 'google.genai') if m in sys.modules))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return {m for m in result.stdout.strip().split(",") if m}


def test_importing_the_package_does_not_load_llm():
    assert modules_loaded_after("import agentic_app") == set()


def test_importing_the_app_does_not_load_llm():
    assert modules_loaded_after("import agentic_app.app") == set()


def test_cli_still_answers(monkeypatch, capsys):
    def no_network():
        raise RuntimeError("the real Gemini client must not be used in tests")

    monkeypatch.setattr(agentic_app.llm, "get_client", no_network)
    monkeypatch.setattr(agentic_app.llm, "generate", lambda prompt, **_: f"echo: {prompt}")
    monkeypatch.setattr(sys, "argv", ["agentic-app", "hello", "world"])

    agentic_app.main()

    assert capsys.readouterr().out == "echo: hello world\n"


def test_cli_without_question_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agentic-app"])
    with pytest.raises(SystemExit):
        agentic_app.main()
