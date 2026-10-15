"""Model clients. Standard library only; the key comes from ANTHROPIC_API_KEY, never from code."""
import json
import os
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"


class LLMError(Exception):
    pass


def _api_error_detail(exc: urllib.error.HTTPError) -> str:
    """The API's own error type and message. Never includes request headers (the key)."""
    try:
        err = json.loads(exc.read().decode("utf-8", "replace")).get("error", {})
        return f"{err.get('type', 'error')}: {err.get('message', '')}".strip()
    except Exception:
        return ""


class AnthropicClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 max_tokens: int = 600, timeout: int = 30, tries: int = 2):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self.model = model or os.environ.get("HEATWATCH_MODEL", DEFAULT_MODEL)
        self.max_tokens, self.timeout, self.tries = max_tokens, timeout, tries

    def complete(self, system: str, messages: list[dict]) -> str:
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens,
                           "system": system, "messages": messages}).encode()
        headers = {"content-type": "application/json", "x-api-key": self.api_key,
                   "anthropic-version": API_VERSION}
        last: Exception | None = None
        detail = ""
        for attempt in range(self.tries):
            try:
                req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.load(r)
                return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            except urllib.error.HTTPError as exc:
                last = exc
                detail = _api_error_detail(exc)
                if exc.code not in (429, 500, 502, 503, 529):
                    break
            except (urllib.error.URLError, TimeoutError) as exc:
                last = exc
            time.sleep(1.5 * (attempt + 1))
        if isinstance(last, urllib.error.HTTPError):
            raise LLMError(f"model request failed: HTTP {last.code} {detail}")
        raise LLMError(f"model request failed: {type(last).__name__}")


class ScriptedClient:
    """Returns prepared replies in order. For tests and offline demos."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, system: str, messages: list[dict]) -> str:
        self.calls.append({"system": system, "messages": list(messages)})
        if not self.replies:
            raise LLMError("no scripted reply left")
        return self.replies.pop(0)
