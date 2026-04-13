import os
import uuid
import logging
import psycopg2
import psycopg2.extras
from typing import List, Dict, Any
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)


class PostgresqlPlugin(StoragePlugin):
    def __init__(self):
        self.host     = os.environ.get("POSTGRES_HOST", "postgres")
        self.port     = os.environ.get("POSTGRES_PORT", "5432")
        self.database = os.environ.get("POSTGRES_DB", "stelr")
        self.user     = os.environ.get("POSTGRES_USER", "stelr")
        self.password = os.environ.get("POSTGRES_PASSWORD", "stelr")
        self._bootstrap()

    def _dsn(self, database: str = None) -> str:
        db = database or self.database
        return (
            f"host={self.host} port={self.port} dbname={db} "
            f"user={self.user} password={self.password}"
        )

    def _conn(self, database: str = None):
        return psycopg2.connect(self._dsn(database))

    def _bootstrap(self):
        # 1. Create the database if it doesn't exist.
        #    Connect to the default 'postgres' maintenance db first.
        try:
            conn = self._conn(database="postgres")
            conn.autocommit = True          # CREATE DATABASE cannot run in a transaction
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s",
                (self.database,)
            )
            exists = cur.fetchone()
            if not exists:
                logger.info(f"[postgresql] Database '{self.database}' not found — creating.")
                cur.execute(f'CREATE DATABASE "{self.database}"')
            else:
                logger.info(f"[postgresql] Database '{self.database}' already exists.")
            cur.close()
            conn.close()
        except Exception as e:
            raise RuntimeError(
                f"[postgresql] Could not connect to maintenance DB or create database: {e}"
            )

        # 2. Create the table if it doesn't exist
        try:
            conn = self._conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    id    VARCHAR(36)  PRIMARY KEY,
                    title VARCHAR(512) NOT NULL,
                    url   TEXT         NOT NULL,
                    rank  INT          DEFAULT 0
                )
            """)
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM links")
            count = cur.fetchone()[0]
            cur.close()
            conn.close()
            logger.info(f"[postgresql] Table 'links' ready ({count} existing rows).")
        except Exception as e:
            raise RuntimeError(f"[postgresql] Could not create table: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, title, url, rank FROM links ORDER BY rank ASC")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows

    def add(self, link: Dict[str, Any]) -> str:
        conn = self._conn()
        cur = conn.cursor()
        link_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO links (id, title, url, rank) VALUES (%s, %s, %s, %s)",
            (link_id, link["title"], link["url"], link.get("rank", 0))
        )
        conn.commit()
        cur.close()
        conn.close()
        return link_id

    def delete(self, link_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM links WHERE id = %s", (link_id,))
        conn.commit()
        cur.close()
        conn.close()

    def update(self, link_id: str, link: Dict[str, Any]):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE links SET title=%s, url=%s, rank=%s WHERE id=%s",
            (link["title"], link["url"], link.get("rank", 0), link_id)
        )
        conn.commit()
        cur.close()
        conn.close()
