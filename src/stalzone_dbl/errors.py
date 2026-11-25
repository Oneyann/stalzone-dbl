"""Library exceptions."""

from __future__ import annotations

from typing import Optional


class DatabaseLookupError(Exception):
    """Base class for all library errors."""


class GitHubError(DatabaseLookupError):
    """A GitHub request failed."""

    def __init__(self, message: str, status: Optional[int] = None, url: str = "") -> None:
        self.status = status
        self.url = url
        super().__init__(message)


class NotFoundError(GitHubError):
    """The requested file does not exist."""


class RateLimitError(GitHubError):
    """The GitHub API rate limit is exhausted."""
