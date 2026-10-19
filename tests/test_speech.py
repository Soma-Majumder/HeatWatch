import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from app.intake import __main__ as cli
from app.intake import speech


class VoiceTests(unittest.TestCase):
    def test_voice_follows_language(self):
        self.assertEqual(speech.voice_for("en"), "Samantha")
        self.assertEqual(speech.voice_for("es"), "Monica")

    def test_unknown_or_missing_language_falls_back_to_english(self):
        self.assertEqual(speech.voice_for(None), "Samantha")
        self.assertEqual(speech.voice_for("fr"), "Samantha")

    def test_speak_calls_say_with_voice_and_text(self):
        with mock.patch("app.intake.speech.subprocess.run") as run:
            speech.speak("Hola", "es")
        run.assert_called_once_with(["say", "-v", "Monica", "Hola"], check=False)

    def test_speak_skips_empty_text(self):
        with mock.patch("app.intake.speech.subprocess.run") as run:
            speech.speak("", "en")
        run.assert_not_called()

    def test_speak_swallows_missing_say(self):
        with mock.patch("app.intake.speech.subprocess.run", side_effect=FileNotFoundError):
            speech.speak("hello", "en")  # must not raise


class FlagTests(unittest.TestCase):
    def test_missing_say_falls_back_to_text_only(self):
        err = io.StringIO()
        with mock.patch.object(cli, "say_available", return_value=False), \
                mock.patch.object(cli, "AnthropicClient", side_effect=cli.LLMError("no key")), \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = cli.main(["--speak"])
        self.assertEqual(rc, 1)  # stopped only because the model key is missing
        self.assertIn("text only", err.getvalue())


if __name__ == "__main__":
    unittest.main()
