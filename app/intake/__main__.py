"""Terminal chat for trying the intake agent:  python3 -m app.intake [--speak]"""
import argparse
import sys

from ..db import connect, init_db
from .agent import IntakeSession
from .llm import AnthropicClient, LLMError
from .speech import say_available, speak


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m app.intake")
    parser.add_argument("--speak", action="store_true",
                        help="read each message aloud (macOS `say`; English and Spanish voices)")
    args = parser.parse_args(argv)
    speaking = args.speak
    if speaking and not say_available():
        print("--speak needs the macOS `say` command, which was not found. Continuing as text only.",
              file=sys.stderr)
        speaking = False
    try:
        llm = AnthropicClient()
    except LLMError as exc:
        print(f"Cannot start: {exc}. Set ANTHROPIC_API_KEY and try again.")
        return 1
    conn = connect()
    init_db(conn)
    session = IntakeSession(llm, conn)
    greeting = session.start()
    print(greeting)
    if speaking:
        speak(greeting, "en")
    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        result = session.step(text)
        if session.last_error:
            print(f"[model problem: {session.last_error}]", file=sys.stderr)
        print(result.message)
        if speaking:
            speak(result.message, session.fields.get("lang", "en"))
        if result.done:
            return 0


if __name__ == "__main__":
    sys.exit(main())
