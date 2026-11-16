# -*- coding: utf-8 -*-
"""Custom exceptions for Bee AI Enterprises ADK."""

class MissingFinalDraftError(RuntimeError):
    """Raised when the main agent fails to produce a valid final draft event."""
    pass
