"""Async lookup for the official Stalzone database."""

from __future__ import annotations

from .version import __version__

from .errors import (
    DatabaseLookupError,
    GitHubError,
    NotFoundError,
    RateLimitError,
)
from .github import GitHubClient
from .index import Entity, Entities, IndexFile, Lookup, SearchIndex
from .lookup import (
    ALL_INDEX_FILES,
    ALL_REALMS_KEYWORDS,
    CommitState,
    DatabaseLookup,
    Realm,
)
from .recipes import BarterIndex, HideoutIndex

__all__ = (
    "DatabaseLookup",
    "GitHubClient",
    "SearchIndex",
    "BarterIndex",
    "HideoutIndex",
    "Lookup",
    "CommitState",
    "IndexFile",
    "Realm",
    "ALL_REALMS_KEYWORDS",
    "ALL_INDEX_FILES",
    "Entity",
    "Entities",
    "DatabaseLookupError",
    "GitHubError",
    "NotFoundError",
    "RateLimitError",
    "__version__",
)
