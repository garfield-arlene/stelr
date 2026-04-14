import os
import uuid
import logging
import mysql.connector
from typing import List, Dict, Any, Optional
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
        return mysql.connector.connect(
            host=self.host, port=self.port,
            user=self.user, password=self.password)

    def _conn(self):
        return mysql.connector.connect(
            host=self.host, port=self.port,
            user=self.user, password=self.password,
            database=self.database)

    def _bootstrap(self):
        try:
            conn = self._root_conn()
            cur = conn.cursor()
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"[mysql] Database '{self.database}' ready.")
        except Exception as e:
            raise RuntimeError(f"[mysql] Could not create database: {e}")

        try:
            conn = self._conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            VARCHAR(36)  PRIMARY KEY,
                    username      VARCHAR(128) NOT NULL UNIQUE,
                    password_hash VARCHAR(256) NOT NULL,
                    is_admin      TINYINT(1)   DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    id      VARCHAR(36)  PRIMARY KEY,
                    user_id VARCHAR(36)  NOT NULL,
                    title   VARCHAR(512) NOT NULL,
                    url     TEXT         NOT NULL,
                    rank    INT          DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"[mysql] Tables ready.")
        except Exception as e:
            raise RuntimeError(f"[mysql] Could not create tables: {e}")

    # ── Users ──────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE id=%s",
                    (user_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            row["is_admin"] = bool(row["is_admin"])
        return row

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s",
                    (username,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            row["is_admin"] = bool(row["is_admin"])
        return row

    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> str:
        conn = self._conn()
        cur = conn.cursor()
        user_id = str(uuid.uuid4())
        cur.execute("INSERT INTO users (id, username, password_hash, is_admin) VALUES (%s,%s,%s,%s)",
                    (user_id, username, password_hash, int(is_admin)))
        conn.commit()
        cur.close(); conn.close()
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, is_admin FROM users ORDER BY username")
        rows = cur.fetchall()
        cur.close(); conn.close()
        for r in rows:
            r["is_admin"] = bool(r["is_admin"])
        return rows

    def delete_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        cur.close(); conn.close()

    # ── Links ──────────────────────────────────────────────────────────────

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, user_id, title, url, rank FROM links "
                    "WHERE user_id=%s ORDER BY rank ASC", (user_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT l.id, l.user_id, u.username, l.title, l.url, l.rank "
                    "FROM links l JOIN users u ON l.user_id=u.id ORDER BY u.username, l.rank")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows

    def add(self, link: Dict[str, Any]) -> str:
        conn = self._conn()
        cur = conn.cursor()
        link_id = str(uuid.uuid4())
        cur.execute("INSERT INTO links (id, user_id, title, url, rank) VALUES (%s,%s,%s,%s,%s)",
                    (link_id, link["user_id"], link["title"], link["url"], link.get("rank", 0)))
        conn.commit()
        cur.close(); conn.close()
        return link_id

    def delete(self, link_id: str, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM links WHERE id=%s AND user_id=%s", (link_id, user_id))
        conn.commit()
        cur.close(); conn.close()

    def update(self, link_id: str, link: Dict[str, Any], user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE links SET title=%s, url=%s, rank=%s WHERE id=%s AND user_id=%s",
                    (link["title"], link["url"], link.get("rank", 0), link_id, user_id))
        conn.commit()
        cur.close(); conn.close()
