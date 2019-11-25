from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""

    def _get_db_name(self, key: str) -> str:
        return f'file:{key}?mode=memory&cache=shared'
