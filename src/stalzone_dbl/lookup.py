"""Async access to the official Stalzone database."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Callable, Optional

from .github import GitHubClient
from .index import INDEX_FILES, Entities, Entity, IndexFile, Lookup, SearchIndex
from .recipes import BARTER_FILE, HIDEOUT_FILE, BarterIndex, HideoutIndex


class Realm:
    """Game version with a separate database."""

    RU = "ru"
    GLOBAL = "global"


REALMS = (Realm.RU, Realm.GLOBAL)
ALL_REALMS_KEYWORDS = ("all", "any", "*")
ALL_INDEX_FILES = [
    f"{realm}/{filename}" for realm in REALMS for filename in INDEX_FILES
]
TOKEN_ENV = ("STALZONE_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")


class TTLCache:
    """Small LRU cache with per-entry TTL."""

    def __init__(self, maxsize: int = 128, ttl: float = 0.0) -> None:
        self._maxsize = max(0, int(maxsize))
        self._ttl = max(0.0, float(ttl))
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _alive(self, expires_at: float) -> bool:
        return self._ttl > 0 and time.monotonic() < expires_at

    def __contains__(self, key: Any) -> bool:
        entry = self._data.get(key)
        if entry is None:
            return False
        if self._alive(entry[1]):
            return True
        del self._data[key]
        return False

    def __getitem__(self, key: Any) -> Any:
        if key not in self:
            raise KeyError(key)
        value, expires_at = self._data.pop(key)
        self._data[key] = (value, expires_at)
        return value

    def __setitem__(self, key: Any, value: Any) -> None:
        self._data.pop(key, None)
        if self._maxsize <= 0 or self._ttl <= 0:
            return

        while self._data:
            oldest, (_, expires_at) = next(iter(self._data.items()))
            if self._alive(expires_at) and len(self._data) < self._maxsize:
                break
            self._data.pop(oldest, None)

        self._data[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class CommitState:
    """Local and remote commit hashes with a TTL for the remote one."""

    _time_offset = time.time() - time.monotonic()

    def __init__(self, ttl: float, local: str = "") -> None:
        self.local = local
        self._ttl = max(0.0, float(ttl))
        self._remote = ""
        self._until = 0.0

    @property
    def remote(self) -> str:
        if time.monotonic() > self._until:
            return ""
        return self._remote

    @remote.setter
    def remote(self, value: str) -> None:
        self._remote = value
        self._until = time.monotonic() + self._ttl if self._ttl > 0 else float("inf")

    @property
    def uptodate(self) -> bool:
        if not self.local or time.monotonic() > self._until:
            return False
        return self.local == self._remote

    @property
    def until(self) -> Optional[datetime]:
        if self._until in (float("inf"), 0.0):
            return None
        return datetime.fromtimestamp(self._until + self._time_offset)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(local={self.local!r}, "
            f"remote={self.remote!r}, uptodate={self.uptodate}, until={self.until})"
        )


class DatabaseLookup:
    """Search and load data from the official Stalzone database."""

    def __init__(
        self,
        github: Optional[GitHubClient] = None,
        token: Optional[str] = None,
        realm: Optional[str] = None,
        threshold: float = 0.5,
        stale_time: float = 900,
        asset_ttl: float = 86400,
        asset_capacity: int = 128,
        sync_on_update: bool = True,
    ) -> None:
        if github is None:
            token = token or next(
                (os.environ[name] for name in TOKEN_ENV if os.environ.get(name)),
                None,
            )
            github = GitHubClient(token=token)

        self._github = github
        self._realm = realm
        self._threshold = self._clamp(threshold)
        self._stale_time = max(0.0, float(stale_time))
        self._asset_ttl = max(0.0, float(asset_ttl))
        self._asset_cap = max(0, int(asset_capacity))
        self._sync_on_update = bool(sync_on_update)

        self._state = CommitState(ttl=self._stale_time)
        self._assets = TTLCache(maxsize=self._asset_cap, ttl=self._asset_ttl)
        self._recipes = TTLCache(maxsize=4, ttl=self._asset_ttl)
        self._indexes: dict[str, SearchIndex] = {}

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def state(self) -> CommitState:
        return self._state

    async def sync(self, force: bool = False, realm: Optional[str] = None) -> bool:
        """Load indexes for one realm or for all realms."""

        async with self._lock("sync"):
            await self._validate_remote_commit(force=force)
            targets = self._targets(realm)

            if (
                not force
                and self._state.uptodate
                and all(path in self._indexes for path in targets)
            ):
                return False

            self._update_commit()
            await asyncio.gather(*(self._download_index(path) for path in targets))
            return True

    async def search(
        self,
        query: str,
        filename: str = IndexFile.LISTING,
        realm: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> list[Lookup]:
        """Return matches sorted by score."""

        index = await self._get_index(self._path(filename, realm))
        limit = self._threshold if threshold is None else self._clamp(threshold)
        return index.search(query, limit)

    async def find_one(
        self,
        query: str,
        filename: str = IndexFile.LISTING,
        realm: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> Optional[Lookup]:
        """Return the best match or ``None``."""

        results = await self.search(
            query=query,
            filename=filename,
            realm=realm,
            threshold=threshold,
        )
        return results[0] if results else None

    async def get_entity(
        self,
        entity_id: str,
        filename: str = IndexFile.LISTING,
        realm: Optional[str] = None,
    ) -> Optional[Entity]:
        """Return entity data by internal id."""

        index = await self._get_index(self._path(filename, realm))
        return index.get(entity_id)

    async def get_all(
        self,
        filename: str = IndexFile.LISTING,
        realm: Optional[str] = None,
    ) -> Entities:
        """Return all entities as ``{id: data}``."""

        index = await self._get_index(self._path(filename, realm))
        return index.all()

    async def item_info(
        self,
        path: str,
        upgrade_level: int = 0,
        realm: Optional[str] = None,
    ) -> Any:
        """Download and cache an item JSON file."""

        path = f"{self._resolve_realm(realm)}/{self._clean_path(path)}"
        level = self._level(upgrade_level)
        if level > 0:
            item = PurePosixPath(path)
            path = (
                item.parent / f"_variants/{item.stem}/{level}.json"
            ).as_posix()

        if path in self._assets:
            return self._assets[path]

        data = json.loads(await self._github.rawfile(path=path))
        self._assets[path] = data
        return data

    async def item_icon(
        self,
        path: str,
        realm: Optional[str] = None,
    ) -> bytes:
        """Download and cache an item icon."""

        path = f"{self._resolve_realm(realm)}/{self._clean_path(path)}"
        if path in self._assets:
            return self._assets[path]

        data = await self._github.rawfile(path=path)
        self._assets[path] = data
        return data

    async def barter_recipes(
        self,
        realm: Optional[str] = None,
        *,
        refresh: bool = False,
    ) -> list[Any]:
        """Return the full ``barter_recipes.json`` payload."""

        index = await self._recipe_index(BARTER_FILE, realm, refresh, BarterIndex)
        return index.data

    async def hideout_recipes(
        self,
        realm: Optional[str] = None,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Return the full ``hideout_recipes.json`` payload."""

        index = await self._recipe_index(
            HIDEOUT_FILE, realm, refresh, HideoutIndex
        )
        return index.data

    async def barter_offers(
        self,
        item_id: str,
        realm: Optional[str] = None,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return barter offers that reward ``item_id``."""

        item_id = self._clean_id(item_id)
        index = await self._recipe_index(BARTER_FILE, realm, refresh, BarterIndex)
        return index.offers(item_id)

    async def barter_uses(
        self,
        item_id: str,
        realm: Optional[str] = None,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return barter offers that require ``item_id``."""

        item_id = self._clean_id(item_id)
        index = await self._recipe_index(BARTER_FILE, realm, refresh, BarterIndex)
        return index.uses(item_id)

    async def hideout_recipes_for(
        self,
        item_id: str,
        realm: Optional[str] = None,
        *,
        refresh: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return hideout recipes that produce or consume ``item_id``."""

        item_id = self._clean_id(item_id)
        index = await self._recipe_index(
            HIDEOUT_FILE, realm, refresh, HideoutIndex
        )
        return {
            "produces": index.produces(item_id),
            "uses": index.uses(item_id),
        }

    async def close(self) -> None:
        """No-op kept for API symmetry."""

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(realm={self._realm!r}, "
            f"threshold={self._threshold}, uptodate={self._state.uptodate}, "
            f"sync_on_update={self._sync_on_update}, "
            f"stale_time={self._stale_time}, asset_ttl={self._asset_ttl})"
        )

    def _resolve_realm(self, realm: Optional[str]) -> str:
        value = str(realm or self._realm or Realm.RU).lower()
        if value not in REALMS:
            raise ValueError(f"Unknown realm {value!r}; expected one of {REALMS}")
        return value

    def _path(self, filename: str, realm: Optional[str]) -> str:
        value = str(filename)
        if value not in INDEX_FILES:
            raise ValueError(
                f"Unknown index file {value!r}; expected one of {INDEX_FILES}"
            )
        return f"{self._resolve_realm(realm)}/{value}"

    def _targets(self, realm: Optional[str]) -> list[str]:
        if realm is not None and str(realm).lower() in ALL_REALMS_KEYWORDS:
            return list(ALL_INDEX_FILES)
        return [
            f"{self._resolve_realm(realm)}/{filename}"
            for filename in INDEX_FILES
        ]

    def _lock(self, key: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._locks.clear()

        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def _get_index(self, path: str) -> SearchIndex:
        await self._validate_remote_commit()

        if self._state.uptodate and path in self._indexes:
            return self._indexes[path]

        if self._sync_on_update:
            await self.sync()
        else:
            async with self._lock("commit"):
                self._update_commit()

        return await self._download_index(path)

    async def _recipe_index(
        self,
        filename: str,
        realm: Optional[str],
        refresh: bool,
        factory: Callable[[Any], Any],
    ) -> Any:
        path = f"{self._resolve_realm(realm)}/{filename}"

        if not refresh and path in self._recipes:
            return self._recipes[path]

        async with self._lock(f"recipe:{path}"):
            if not refresh and path in self._recipes:
                return self._recipes[path]

            data = json.loads(await self._github.rawfile(path=path))
            index = factory(data)
            self._recipes[path] = index
            return index

    async def _download_index(self, path: str) -> SearchIndex:
        async with self._lock(path):
            index = self._indexes.get(path)
            if index is not None and self._state.uptodate:
                return index

            data = json.loads(await self._github.rawfile(path=path))
            index = SearchIndex()
            index.build(path, data)
            self._indexes[path] = index
            return index

    async def _validate_remote_commit(self, force: bool = False) -> None:
        if self._state.remote and not force:
            return

        async with self._lock("commit"):
            if force or not self._state.remote:
                self._state.remote = await self._github.latest_commit()

    def _update_commit(self) -> None:
        if not self._state.uptodate:
            self._state.local = self._state.remote
            self._indexes.clear()
            self._assets.clear()
            self._recipes.clear()

    @staticmethod
    def _clean_id(item_id: str) -> str:
        value = str(item_id).strip()
        if not value:
            raise ValueError("item id must not be empty")
        return value

    @staticmethod
    def _clean_path(path: str) -> str:
        value = str(path).strip().lstrip("/")
        if not value:
            raise ValueError("path must not be empty")
        return value

    @staticmethod
    def _level(value: int) -> int:
        try:
            level = int(value)
        except (TypeError, ValueError):
            raise ValueError("upgrade_level must be an integer") from None
        return max(0, min(15, level))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
