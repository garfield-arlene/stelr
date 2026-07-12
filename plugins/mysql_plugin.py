import os
import uuid
import logging
import mysql.connector
import mysql.connector.pooling
from typing import List, Dict, Any, Optional
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)


class MysqlPlugin(StoragePlugin):
    def __init__(self):
        self.host      = os.environ.get("MYSQL_HOST", "mysql")
        self.port      = int(os.environ.get("MYSQL_PORT", "3306"))
        self.user      = os.environ.get("MYSQL_USER", "stelr")
        self.password  = os.environ.get("MYSQL_PASSWORD", "stelr")
        self.database  = os.environ.get("MYSQL_DATABASE", "stelr")
        self.pool_size = int(os.environ.get("MYSQL_POOL_SIZE", "10"))
        self._ensure_database()
        self._pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="stelr_pool", pool_size=self.pool_size, autocommit=True,
            host=self.host, port=self.port,
            user=self.user, password=self.password,
            database=self.database)
        self._create_tables()

    def _root_conn(self):
        return mysql.connector.connect(
            host=self.host, port=self.port,
            user=self.user, password=self.password)

    def _conn(self):
        return self._pool.get_connection()

    def _ensure_database(self):
        try:
            conn = self._root_conn()
            cur = conn.cursor()
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            cur.close(); conn.close()
        except Exception as e:
            raise RuntimeError(f"[mysql] Could not create database: {e}")

    def _create_tables(self):
        try:
            conn = self._conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            VARCHAR(36)  PRIMARY KEY,
                    username      VARCHAR(128) NOT NULL UNIQUE,
                    password_hash VARCHAR(256) NOT NULL,
                    is_admin      TINYINT(1)   DEFAULT 0,
                    approved      TINYINT(1)   DEFAULT 1
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    id      VARCHAR(36)  PRIMARY KEY,
                    user_id VARCHAR(36)  NOT NULL,
                    title   VARCHAR(512) NOT NULL,
                    url     TEXT         NOT NULL,
                    `rank`  INT          DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    `key`   VARCHAR(128) PRIMARY KEY,
                    `value` TEXT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `groups` (
                    id      VARCHAR(36)  PRIMARY KEY,
                    user_id VARCHAR(36)  NOT NULL,
                    name    VARCHAR(256) NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Migrate: add approved column if missing
            cur.execute("SHOW COLUMNS FROM users LIKE 'approved'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD COLUMN approved TINYINT(1) DEFAULT 1")
            # Migrate: add group_id column if missing
            cur.execute("SHOW COLUMNS FROM links LIKE 'group_id'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE links ADD COLUMN group_id VARCHAR(36) NULL")
            cur.close(); conn.close()
            logger.info("[mysql] Tables ready.")
        except Exception as e:
            raise RuntimeError(f"[mysql] Could not create tables: {e}")

    # ── Settings ───────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT `value` FROM settings WHERE `key`=%s", (key,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("REPLACE INTO settings (`key`, `value`) VALUES (%s, %s)", (key, value))
        cur.close(); conn.close()

    # ── Users ──────────────────────────────────────────────────────────────

    def _row(self, row) -> Dict[str, Any]:
        return {**row, "is_admin": bool(row["is_admin"]), "approved": bool(row["approved"])}

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, is_admin, approved "
                    "FROM users WHERE id=%s AND approved=1", (user_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return self._row(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, is_admin, approved "
                    "FROM users WHERE username=%s AND approved=1", (username,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return self._row(row) if row else None

    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False, approved: bool = True) -> str:
        conn = self._conn()
        cur = conn.cursor()
        user_id = str(uuid.uuid4())
        cur.execute("INSERT INTO users (id, username, password_hash, is_admin, approved) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (user_id, username, password_hash, int(is_admin), int(approved)))
        cur.close(); conn.close()
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, is_admin, approved FROM users "
                    "WHERE approved=1 ORDER BY username")
        rows = [self._row(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return rows

    def delete_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        cur.close(); conn.close()

    def set_password(self, user_id: str, password_hash: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (password_hash, user_id))
        cur.close(); conn.close()

    def get_pending_users(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, is_admin, approved FROM users "
                    "WHERE approved=0 ORDER BY username")
        rows = [self._row(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return rows

    def approve_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE users SET approved=1 WHERE id=%s", (user_id,))
        cur.close(); conn.close()

    def reject_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s AND approved=0", (user_id,))
        cur.close(); conn.close()

    # ── Links ──────────────────────────────────────────────────────────────

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, user_id, title, url, `rank`, group_id FROM links "
                    "WHERE user_id=%s ORDER BY `rank`", (user_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT l.id, l.user_id, u.username, l.title, l.url, l.`rank`, l.group_id "
                    "FROM links l JOIN users u ON l.user_id=u.id ORDER BY u.username, l.`rank`")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows

    def add(self, link: Dict[str, Any]) -> str:
        conn = self._conn()
        cur = conn.cursor()
        link_id = str(uuid.uuid4())
        cur.execute("INSERT INTO links (id, user_id, title, url, `rank`, group_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (link_id, link["user_id"], link["title"], link["url"],
                     link.get("rank", 0), link.get("group_id") or None))
        cur.close(); conn.close()
        return link_id

    def delete(self, link_id: str, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM links WHERE id=%s AND user_id=%s", (link_id, user_id))
        cur.close(); conn.close()

    def update(self, link_id: str, link: Dict[str, Any], user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE links SET title=%s, url=%s, `rank`=%s, group_id=%s "
                    "WHERE id=%s AND user_id=%s",
                    (link["title"], link["url"], link.get("rank", 0),
                     link.get("group_id") or None, link_id, user_id))
        cur.close(); conn.close()

    # ── Groups ─────────────────────────────────────────────────────────────

    def get_groups(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, user_id, name FROM `groups` WHERE user_id=%s ORDER BY name", (user_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows

    def create_group(self, user_id: str, name: str) -> str:
        conn = self._conn()
        cur = conn.cursor()
        group_id = str(uuid.uuid4())
        cur.execute("INSERT INTO `groups` (id, user_id, name) VALUES (%s,%s,%s)",
                    (group_id, user_id, name))
        cur.close(); conn.close()
        return group_id

    def rename_group(self, group_id: str, user_id: str, name: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE `groups` SET name=%s WHERE id=%s AND user_id=%s",
                    (name, group_id, user_id))
        cur.close(); conn.close()

    def delete_group(self, group_id: str, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM `groups` WHERE id=%s AND user_id=%s", (group_id, user_id))
        if cur.rowcount:
            cur.execute("UPDATE links SET group_id=NULL WHERE group_id=%s", (group_id,))
        cur.close(); conn.close()
