"""Barter and hideout recipe indexes."""

from __future__ import annotations

from typing import Any

BARTER_FILE = "barter_recipes.json"
HIDEOUT_FILE = "hideout_recipes.json"


class BarterIndex:
    """Barter offers grouped by the item they reward or consume."""

    def __init__(self, data: Any) -> None:
        if not isinstance(data, list):
            raise ValueError(f"{BARTER_FILE} must contain a JSON array")

        self.data: list[Any] = data
        self._rewards: dict[str, list[dict[str, Any]]] = {}
        self._uses: dict[str, list[dict[str, Any]]] = {}
        self._build()

    def _build(self) -> None:
        for settlement in self.data:
            if not isinstance(settlement, dict):
                continue

            title = settlement.get("settlementTitle")
            if not isinstance(title, dict):
                title = {}

            recipes = settlement.get("recipes")
            if not isinstance(recipes, list):
                continue

            for recipe in recipes:
                if not isinstance(recipe, dict):
                    continue

                item = recipe.get("item")
                if not isinstance(item, str) or not item:
                    continue

                offers = recipe.get("offers")
                if not isinstance(offers, list):
                    continue

                for offer in offers:
                    if not isinstance(offer, dict):
                        continue

                    entry = {
                        "item": item,
                        "settlement": title,
                        "level": recipe.get("settlementRequiredLevel"),
                        "currency": offer.get("currency"),
                        "cost": offer.get("cost"),
                        "requiredItems": _required_items(
                            offer.get("requiredItems")
                        ),
                    }
                    self._rewards.setdefault(item, []).append(entry)
                    for required_id in {
                        required["item"] for required in entry["requiredItems"]
                    }:
                        self._uses.setdefault(required_id, []).append(entry)

    def offers(self, item_id: str) -> list[dict[str, Any]]:
        """Offers that reward ``item_id``."""

        return list(self._rewards.get(item_id, ()))

    def uses(self, item_id: str) -> list[dict[str, Any]]:
        """Offers that require ``item_id``."""

        return list(self._uses.get(item_id, ()))

    def __len__(self) -> int:
        return len(self._rewards)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(items={len(self._rewards)})"


class HideoutIndex:
    """Hideout recipes grouped by produced and consumed items."""

    def __init__(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError(f"{HIDEOUT_FILE} must contain a JSON object")

        recipes = data.get("recipes")
        if not isinstance(recipes, list):
            raise ValueError(f"{HIDEOUT_FILE} has no recipes array")

        self.data: dict[str, Any] = data
        perks = data.get("perks")
        self.perks: list[Any] = perks if isinstance(perks, list) else []
        self._produces: dict[str, list[dict[str, Any]]] = {}
        self._uses: dict[str, list[dict[str, Any]]] = {}
        self._build(recipes)

    def _build(self, recipes: list[Any]) -> None:
        for recipe in recipes:
            if not isinstance(recipe, dict):
                continue

            produced = _item_ids(recipe.get("result"))
            consumed = _item_ids(recipe.get("ingredients"))
            if not produced and not consumed:
                continue

            for item in produced:
                self._produces.setdefault(item, []).append(recipe)
            for item in consumed:
                self._uses.setdefault(item, []).append(recipe)

    def produces(self, item_id: str) -> list[dict[str, Any]]:
        """Recipes that produce ``item_id``."""

        return list(self._produces.get(item_id, ()))

    def uses(self, item_id: str) -> list[dict[str, Any]]:
        """Recipes that consume ``item_id``."""

        return list(self._uses.get(item_id, ()))

    def __len__(self) -> int:
        return len(self._produces)

    def __repr__(self) -> str:
        recipes = self.data.get("recipes")
        count = len(recipes) if isinstance(recipes, list) else 0
        return f"{self.__class__.__name__}(recipes={count})"


def _item_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return list(
        dict.fromkeys(
            entry["item"]
            for entry in value
            if isinstance(entry, dict)
            and isinstance(entry.get("item"), str)
            and entry["item"]
        )
    )


def _required_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    result = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        item = entry.get("item")
        if not isinstance(item, str) or not item:
            continue
        result.append({"item": item, "amount": entry.get("amount")})
    return result
