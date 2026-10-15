"""Idempotent additive migration for installations created before plugin states."""
from tortoise import Tortoise


async def migrate_plugin_state():
    connection = Tortoise.get_connection("default")
    columns = {row["name"] for row in await connection.execute_query_dict('PRAGMA table_info("plugins")')}
    additions = {
        "status": "VARCHAR(16) NOT NULL DEFAULT 'loading'",
        "last_error": "TEXT",
        "active_directory": "VARCHAR(1024)",
    }
    for name, definition in additions.items():
        if name not in columns:
            await connection.execute_script(f'ALTER TABLE "plugins" ADD COLUMN "{name}" {definition};')
