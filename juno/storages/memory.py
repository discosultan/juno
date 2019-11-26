from typing import Tuple

from .sqlite import SQLite


class Memory(SQLite):
    """In-memory data storage. Uses SQLite's memory mode for implementation."""

    def _get_db_name(self, key: str) -> Tuple[str, bool]:
        return f'file:{id(self)}_{key}?mode=memory&cache=shared', True
