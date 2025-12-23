from tortoise import Tortoise

from domain.adapters.registry import runtime_registry

TORTOISE_ORM = {
    "connections": {"default": "sqlite://data/db/db.sqlite3"},
    "apps": {
        "models": {
            "models": ["models.database"],
            "default_connection": "default",
        }
    },
}


def patch_aiosqlite_for_tortoise() -> None:
    import aiosqlite

    if hasattr(aiosqlite.Connection, "start"):
        return

    def start(self) -> None:  # type: ignore[no-redef]
        if not self._thread.is_alive():
            self._thread.start()

    aiosqlite.Connection.start = start  # type: ignore[attr-defined]


async def init_db():
    patch_aiosqlite_for_tortoise()
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    await runtime_registry.refresh()


async def close_db():
    await Tortoise.close_connections()
