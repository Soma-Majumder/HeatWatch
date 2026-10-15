"""Terminal chat for trying the intake agent:  python3 -m app.intake"""
import sys

from ..db import connect, init_db
from .agent import IntakeSession
from .llm import AnthropicClient, LLMError


def main() -> int:
    try:
        llm = AnthropicClient()
    except LLMError as exc:
        print(f"Cannot start: {exc}. Set ANTHROPIC_API_KEY and try again.")
        return 1
    conn = connect()
    init_db(conn)
    session = IntakeSession(llm, conn)
    print(session.start())
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
        if result.done:
            return 0


if __name__ == "__main__":
    sys.exit(main())
