import os
import uuid
import psycopg2
import psycopg2.extras
from typing import List, Dict, Any
from plugins.base import StoragePlugin

class PostgresqlPlugin(StoragePlugin):
    def __init__(self):
        self.dsn = (
            f"host={os.environ.get('POSTGRES_HOST', 'postgres')} "
            f"port={os.environ.get('POSTGRES_PORT', '5432')} "
            f"dbname={os.environ.get('POSTGRES_DB', 'stelr')} "
            f"user={os.environ.get('POSTGRES_USER', 'stelr')} "
            f"password={os.environ.get('POSTGRES_PASSWORD', 'stelr')}"
        )
        self._init_db()

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def _init_db(self):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id    VARCHAR(36) PRIMARY KEY,
                title VARCHAR(512) NOT NULL,
                url   TEXT NOT NULL,
                rank  INT DEFAULT 0
            )
        """)
        conn.commit()
        cur.close()
        conn.close()

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
