import sqlite3
import os
from typing import Optional

class DatabaseConnection:
    """Gerencia conexões e transações no banco de dados SQLite local."""

    def __init__(self, db_path: str = "data/locator.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn