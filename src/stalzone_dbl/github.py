"""Minimal async GitHub client built on the standard library."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from .errors import GitHubError, NotFoundError, RateLimitError
from .version import __version__

OWNER = "EXBO-Studio"
REPOSITORY = "stalzone-database"
BRANCH = "main"

API_URL = "https://api.github.com"
RAW_URL = "https://raw.githubusercontent.com"
USER_AGENT = f"stalzone-dbl/{__version__}"

TIMEOUT = 60.0
RETRIES = 3
BACKOFF = 1.5


class GitHubClient:
    """Reads the official database repository from GitHub."""

    def __init__(
        self,
        token: Optional[str] = None,
        owner: str = OWNER,
        repository: str = REPOSITORY,
        branch: str = BRANCH,
        timeout: float = TIMEOUT,
        retries: int = RETRIES,
    ) -> None:
        self._token = token
        self._owner = owner
        self._repository = repository
        self._branch = branch
        self._slug = f"{owner}/{repository}"
        self._timeout = max(1.0, float(timeout))
        self._retries = max(1, int(retries))

        self._headers = {
            "Accept": "application/vnd.github+json",
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    @property
    def slug(self) -> str:
        return self._slug

    async def latest_commit(self) -> str:
        url = f"{API_URL}/repos/{self._slug}/commits/{self._branch}"
        data = await asyncio.to_thread(self._get_json, url)
        try:
            return str(data["sha"])
        except (KeyError, TypeError) as exc:
            raise GitHubError(f"Unexpected commit response from {url}", url=url) from exc

    async def rawfile(self, path: str, ref: Optional[str] = None) -> bytes:
        ref = ref or self._branch
        safe_path = urllib.parse.quote(path.lstrip("/"), safe="/")
        url = f"{RAW_URL}/{self._slug}/{ref}/{safe_path}"
        return await asyncio.to_thread(self._get, url)

    def _get_json(self, url: str) -> Any:
        body = self._get(url)
        try:
            return json.loads(body)
        except ValueError as exc:
            raise GitHubError(f"Invalid JSON from {url}", url=url) from exc

    def _get(self, url: str) -> bytes:
        last_error: Optional[BaseException] = None

        for attempt in range(self._retries):
            request = urllib.request.Request(url, headers=self._headers)
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                detail = self._error_body(exc)
                message = f"GitHub returned HTTP {status} for {url}"
                if detail:
                    message = f"{message}: {detail}"

                if status == 404:
                    raise NotFoundError(message, status=status, url=url) from exc
                if status in (403, 429):
                    raise RateLimitError(
                        f"{message}. Pass a GitHub token to raise the limit.",
                        status=status,
                        url=url,
                    ) from exc
                if status < 500:
                    raise GitHubError(message, status=status, url=url) from exc

                last_error = GitHubError(message, status=status, url=url)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc

            if attempt + 1 < self._retries:
                time.sleep(BACKOFF * (2**attempt))

        raise GitHubError(
            f"Request failed after {self._retries} attempts: {url} ({last_error})",
            url=url,
        )

    @staticmethod
    def _error_body(exc: urllib.error.HTTPError) -> str:
        try:
            return exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            return ""

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(token={self.has_token}, "
            f"repo={self._slug!r}, branch={self._branch!r})"
        )
