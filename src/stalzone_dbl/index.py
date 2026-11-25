"""Text normalization, index parsing and in-memory fuzzy search."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Callable, Iterator, NamedTuple

Entity = dict[str, Any]
Entities = dict[str, Entity]
Row = tuple[str, Entity, list[str]]
Parser = Callable[[list[Any]], Iterator[Row]]


class IndexFile:
    """JSON index file names."""

    LISTING = "listing.json"
    ACHIEVEMENTS = "achievements.json"
    STATS = "stats.json"


INDEX_FILES = (IndexFile.LISTING, IndexFile.ACHIEVEMENTS, IndexFile.STATS)

_NORMALIZE = re.compile(r"[^\w\u0400-\u04FF]+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase text, strip punctuation and collapse spaces."""

    text = unicodedata.normalize("NFKC", text.lower())
    text = _NORMALIZE.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def words(text: str) -> set[str]:
    """Split text into unique normalized words."""

    return {word for word in normalize(text).split(" ") if word}


def ngrams(token: str, n: int = 3) -> set[str]:
    """Build padded N-grams for one word."""

    if not token:
        return set()

    padded = f"#{token}#"
    result = {padded[i : i + n] for i in range(len(padded) - n + 1)}
    if len(token) < n:
        result.add(token)
    return result


def ngramize(text: str) -> set[str]:
    """Build N-grams for every word in text."""

    return {gram for word in words(text) for gram in ngrams(word)}


class Lookup(NamedTuple):
    """One search result."""

    id: str
    data: dict[str, Any]
    score: float = 0.0


class SearchIndex:
    """In-memory inverted index for one JSON file."""

    SCORE_ROUND = 2
    JACCARD_WEIGHT = 0.8

    def __init__(self) -> None:
        self._index: dict[str, set[str]] = {}
        self._entities: Entities = {}
        self._counts: dict[str, int] = {}

    def build(self, path: str, data: Any) -> None:
        index: dict[str, set[str]] = defaultdict(set)
        counts: dict[str, set[str]] = defaultdict(set)
        entities: Entities = {}

        for entity_id, entity, texts in parse(path, data):
            entities[entity_id] = entity
            for text in texts:
                for gram in ngramize(text):
                    index[gram].add(entity_id)
                    counts[entity_id].add(gram)

        self._index = dict(index)
        self._entities = entities
        self._counts = {entity_id: len(grams) for entity_id, grams in counts.items()}

    def get(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def all(self) -> Entities:
        return self._entities.copy()

    def search(self, query: str, threshold: float) -> list[Lookup]:
        grams = ngramize(query)
        if not grams:
            return []

        hits: dict[str, int] = defaultdict(int)
        for gram in grams.intersection(self._index):
            for entity_id in self._index[gram]:
                hits[entity_id] += 1

        query_size = len(grams)
        scored: list[tuple[float, str]] = []

        for entity_id, count in hits.items():
            entity_size = self._counts.get(entity_id, 0)
            min_size = min(query_size, entity_size)
            union_size = query_size + entity_size - count
            overlap = count / min_size if min_size > 0 else 0.0
            jaccard = count / union_size if union_size > 0 else 0.0
            score = max(overlap, jaccard * self.JACCARD_WEIGHT)

            if score >= threshold:
                scored.append((score, entity_id))

        scored.sort(key=lambda row: (-row[0], row[1]))
        return [
            Lookup(
                id=entity_id,
                data=self._entities.get(entity_id, {}),
                score=round(score, self.SCORE_ROUND),
            )
            for score, entity_id in scored
        ]

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(entities={len(self._entities)}, "
            f"index={len(self._index)})"
        )


def parse(path: str, data: Any) -> Iterator[Row]:
    """Yield ``(id, entity, texts)`` rows for a known index file."""

    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")

    filename = path.rsplit("/", 1)[-1]
    if filename == IndexFile.LISTING:
        parser: Parser = _parse_listing
    elif filename == IndexFile.STATS:
        parser = _parse_stats
    elif filename == IndexFile.ACHIEVEMENTS:
        parser = _parse_achievements
    else:
        raise ValueError(f"Unsupported index file: {filename!r}")

    yield from parser(data)


def _parse_listing(data: list[Any]) -> Iterator[Row]:
    for item in data:
        if not isinstance(item, dict):
            continue
        item_path = item.get("data")
        if not isinstance(item_path, str) or not item_path:
            continue

        entity_id = item_path.rsplit("/", 1)[-1]
        if entity_id.endswith(".json"):
            entity_id = entity_id[:-5]
        if not entity_id:
            continue

        yield entity_id, item, _extract(item, "name")


def _parse_stats(data: list[Any]) -> Iterator[Row]:
    return _parse_by_id(data, "name")


def _parse_achievements(data: list[Any]) -> Iterator[Row]:
    return _parse_by_id(data, "title")


def _parse_by_id(data: list[Any], field: str) -> Iterator[Row]:
    for item in data:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("id")
        if not isinstance(entity_id, str) or not entity_id:
            continue
        yield entity_id, item, _extract(item, field)


def _extract(item: Entity, *fields: str) -> list[str]:
    return [text for field in fields for text in _translations(item, field)]


def _translations(item: Entity, field: str) -> list[str]:
    block = item.get(field)
    if not isinstance(block, dict):
        return []

    kind = block.get("type")
    if kind == "translation":
        lines = block.get("lines")
        if not isinstance(lines, dict):
            return []
        return [text for text in lines.values() if isinstance(text, str) and text.strip()]

    if kind == "text":
        text = block.get("text")
        return [text] if isinstance(text, str) and text.strip() else []

    return []
