# stalzone-dbl

Асинхронный нечёткий поиск, предметы и рецепты из официальной базы Stalzone. Без зависимостей.

```bash
pip install stalzone-dbl
```

```python
import asyncio
from stalzone_dbl import DatabaseLookup

async def main():
    lookup = DatabaseLookup()  # или token="ghp_..."
    await lookup.sync()

    for item in await lookup.search("АК-105"):
        print(item.id, item.score, item.data["data"])

    best = await lookup.find_one("Цинк")
    if best:
        print(await lookup.item_info(best.data["data"]))

    for offer in await lookup.barter_offers("nv63"):
        print(offer["settlement"]["lines"]["ru"], offer["level"], offer["cost"])

    craft = await lookup.hideout_recipes_for("okp24")
    print(craft["produces"][0]["ingredients"])

asyncio.run(main())
```

## API

| Метод | Назначение |
| --- | --- |
| `sync(force=False, realm=None)` | Загрузить индексы (`ru`, `global` или `all`) |
| `search(query, filename="listing.json", realm=None, threshold=None)` | Все совпадения по score |
| `find_one(...)` | Лучшее совпадение или `None` |
| `get_entity(id, ...)` | Сущность по внутреннему ID |
| `get_all(...)` | Словарь `{id: данные}` |
| `item_info(path, upgrade_level=0)` | JSON предмета |
| `item_icon(path)` | PNG-иконка |
| `barter_recipes(realm=None, refresh=False)` | Полный `barter_recipes.json` |
| `barter_offers(item_id, ...)` | Бартер: предмет — награда |
| `barter_uses(item_id, ...)` | Бартер: предмет — стоимость |
| `hideout_recipes(realm=None, refresh=False)` | Полный `hideout_recipes.json` (перки и рецепты) |
| `hideout_recipes_for(item_id, ...)` | Убежище: `{"produces": [...], "uses": [...]}` |

Индексы: `listing.json`, `achievements.json`, `stats.json`.
Рецепты загружаются лениво и кешируются вместе с ассетами (`asset_ttl`); `refresh=True` — принудительно обновить.
Параметры: `threshold=0.5`, `stale_time=900`, `asset_ttl=86400`, `asset_capacity=128`, `sync_on_update=True`.

GitHub-токен читается из `STALZONE_GITHUB_TOKEN`, `GITHUB_TOKEN` или `GH_TOKEN`.
Без токена лимит API — 60 запросов в час.

Данные — [EXBO-Studio/stalzone-database](https://github.com/EXBO-Studio/stalzone-database),
исходная идея — [stalcraft-api](https://github.com/onejeuu/stalcraft-api).
