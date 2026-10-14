"""Intake agent: a conversation that turns tenant text into an Intake (issue #14).

The model only extracts fields and phrases questions. Harness code validates
every field, decides when the intake is complete, and creates the ticket.
"""
from .agent import IntakeSession, TurnResult
from .llm import AnthropicClient, LLMError, ScriptedClient

__all__ = ["IntakeSession", "TurnResult", "AnthropicClient", "ScriptedClient", "LLMError"]
