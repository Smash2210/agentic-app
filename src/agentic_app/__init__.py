import sys


def main() -> None:
    # Imported here so importing the package (e.g. the Claims API) does not load .env or Gemini.
    from agentic_app.llm import generate

    if len(sys.argv) < 2:
        print('Usage: agentic-app "your question"', file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    try:
        print(generate(prompt))
    except Exception as exc:  # show a clean message instead of a stack trace
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)