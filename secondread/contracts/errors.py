"""Shared exception types.

Adapters translate provider-specific failures into these so callers never
depend on a provider SDK. Messages must be safe to show a user: never include
API keys or document text.
"""

from __future__ import annotations


class SecondReadError(Exception):
    """Base class for every Second Read error."""


class ProviderError(SecondReadError):
    """An LLM, search or fetch provider failed.

    ``retryable`` is True for transient failures (rate limits, timeouts,
    5xx) that the adapter already retried and gave up on, or that a caller may
    retry later.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class AuthError(ProviderError):
    """The provider rejected the API key (invalid, revoked or out of credit)."""


class RateLimitError(ProviderError):
    """The provider rate-limited us and retries were exhausted."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class SchemaError(ProviderError):
    """Structured output did not validate against the requested schema."""


class FetchError(SecondReadError):
    """A URL could not be fetched (unreachable, too large, bad status)."""


class BlockedURLError(FetchError):
    """A URL was refused by SSRF protection (private IP, bad scheme)."""


class BudgetExceeded(SecondReadError):
    """A token, search-call or time budget ran out."""


class DocumentTooLong(SecondReadError):
    """The document exceeds the size cap."""


class MissingSetup(SecondReadError):
    """No API key or configuration is available for the caller."""
