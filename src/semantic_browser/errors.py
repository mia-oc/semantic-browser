"""Custom exception hierarchy."""


class SemanticBrowserError(Exception):
    """Base error for semantic-browser."""


class BrowserNotReadyError(SemanticBrowserError):
    """Browser objects are unavailable."""


class SessionNotFoundError(SemanticBrowserError):
    """Session ID could not be found."""


class ActionNotFoundError(SemanticBrowserError):
    """Action ID is unknown."""


class ActionStaleError(SemanticBrowserError):
    """Action target no longer exists."""


class ActionExecutionError(SemanticBrowserError):
    """Action failed during execution."""


class SettleTimeoutError(SemanticBrowserError):
    """Page failed to settle in time."""


class ExtractionError(SemanticBrowserError):
    """Extraction pipeline failed."""


class PageUnreliableError(SemanticBrowserError):
    """Page quality is too low for deterministic operation."""


class AttachmentError(SemanticBrowserError):
    """Could not attach to provided browser object or endpoint."""
