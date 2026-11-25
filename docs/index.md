# stalzone-dbl

Асинхронный нечёткий поиск, предметы и рецепты из базы Stalzone. Без зависимостей.

```bash
pip install stalzone-dbl
```

## Быстрый старт

```python
import asyncio
from stalzone_dbl import DatabaseLookup

async def main():
    lookup = DatabaseLookup()
    await lookup.sync()

    for item in await lookup.search("АК-105"):
        print(item.id, item.score, item.data["data"])

    best = await lookup.find_one("Цинк")
    if best:
        print(await lookup.item_info(best.data["data"]))

    craft = await lookup.hideout_recipes_for("okp24")
    print(craft["produces"][0]["ingredients"])

asyncio.run(main())
```

## Методы

| Метод | Назначение |
| --- | --- |
| `sync(force=False, realm=None)` | Загрузка индексов |
| `search(query, ...)` | Все совпадения по score |
| `find_one(...)` | Лучшее совпадение или `None` |
| `get_entity(id, ...)` | Сущность по ID |
| `get_all(...)` | Словарь `{id: данные}` |
| `item_info(path, upgrade_level=0)` | JSON предмета |
| `item_icon(path)` | PNG-иконка |
| `barter_recipes(...)` | Полный `barter_recipes.json` |
| `barter_offers(item_id, ...)` | Бартер: где получить предмет |
| `barter_uses(item_id, ...)` | Бартер: где использовать предмет |
| `hideout_recipes(...)` | Полный `hideout_recipes.json` |
| `hideout_recipes_for(item_id, ...)` | Рецепты убежища: `produces` и `uses` |
