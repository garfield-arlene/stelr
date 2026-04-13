import os
import uuid
import logging
import mysql.connector
from typing import List, Dict, Any
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)


class MysqlPlugin(StoragePlugin):
    def __init__(self):
        self.host     = os.environ.get("MYSQL_HOST", "mysql")
        self.port     = int(os.environ.get("MYSQL_PORT", "3306"))
        self.user     = os.environ.get("MYSQL_USER", "stelr")
        self.password = os.environ.get("MYSQL_PASSWORD", "stelr")
        self.database = os.environ.get("MYSQL_DATABASE", "stelr")
        self._bootstrap()

    def _root_conn(self):
        """Connect without specifying a database (for schema bootstrap)."""
        return mysql.connector.connect(
            host=self.host, port=self.port,
            user=self.user, password=self.password,
        )

    def _conn(self):
        return mysql.connector.connect(
            host=self.host, port=self.port,
            user=self.user, password=self.password,
            database=self.database,
        )

    def _bootstrap(self):
        # 1. Create the database if it doesn't exist
        try:
            conn = self._root_conn()
            cur = conn.cursor()
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"[mysql] Database '{self.database}' ready.")
        except Exception as e:
            raise RuntimeError(f"[mysql] Could not connect or create database: {e}")

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
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM links")
            count = cur.fetchone()[0]
            cur.close()
            conn.close()
            logger.info(f"[mysql] Table 'links' ready ({count} existing rows).")
        except Exception as e:
            raise RuntimeError(f"[mysql] Could not create table: {e}")

    def get_all(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, title, url, rank FROM links ORDER BY rank ASC")
        rows = cur.fetchall()
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
