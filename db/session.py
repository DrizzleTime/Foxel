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

async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    await runtime_registry.refresh()


async def close_db():
    await Tortoise.close_connections()
