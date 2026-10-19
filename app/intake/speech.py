"""Read intake messages aloud with the macOS `say` command (python3 -m app.intake --speak).

Only text that has already passed the guard and the output gate is spoken: callers pass
the message they are about to print. Nothing leaves the machine.
"""
import shutil
import subprocess

VOICES = {"en": "Samantha", "es": "Monica"}


def voice_for(lang: str | None) -> str:
    return VOICES.get(lang or "en", VOICES["en"])


def say_available() -> bool:
    return shutil.which("say") is not None


def speak(text: str, lang: str | None = "en") -> None:
    """Speak `text` and wait for it to finish. A failure to speak never breaks the chat."""
    if not text:
        return
    try:
        subprocess.run(["say", "-v", voice_for(lang), text], check=False)
    except OSError:
        pass
