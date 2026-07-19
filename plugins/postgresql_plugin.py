import os
import uuid
import logging
import psycopg2
import psycopg2.extras
import psycopg2.pool
from typing import List, Dict, Any, Optional
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)


class PostgresqlPlugin(StoragePlugin):
    def __init__(self):
        self.host      = os.environ.get("POSTGRES_HOST", "postgres")
        self.port      = os.environ.get("POSTGRES_PORT", "5432")
        self.database  = os.environ.get("POSTGRES_DB", "stelr")
        self.user      = os.environ.get("POSTGRES_USER", "stelr")
        self.password  = os.environ.get("POSTGRES_PASSWORD", "stelr")
        self.pool_size = int(os.environ.get("POSTGRES_POOL_SIZE", "10"))
        self._bootstrap()
        self._pool = psycopg2.pool.ThreadedConnectionPool(1, self.pool_size, self._dsn())

    def _dsn(self, database=None):
        db = database or self.database
        return (f"host={self.host} port={self.port} dbname={db} "
                f"user={self.user} password={self.password}")

    def _raw_conn(self, database=None):
        return psycopg2.connect(self._dsn(database))

    def _conn(self):
        conn = self._pool.getconn()
        conn.autocommit = True
        return conn

    def _release_conn(self, conn):
        self._pool.putconn(conn)

    def _bootstrap(self):
        try:
            conn = self._raw_conn(database="postgres")
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname=%s", (self.database,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{self.database}"')
            cur.close(); conn.close()
        except Exception as e:
            raise RuntimeError(f"[postgresql] Could not create database: {e}")

        try:
            conn = self._raw_conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            VARCHAR(36)  PRIMARY KEY,
                    username      VARCHAR(128) NOT NULL UNIQUE,
                    password_hash VARCHAR(256) NOT NULL,
                    is_admin      BOOLEAN      DEFAULT FALSE,
                    approved      BOOLEAN      DEFAULT TRUE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    id      VARCHAR(36)  PRIMARY KEY,
                    user_id VARCHAR(36)  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title   VARCHAR(512) NOT NULL,
                    url     TEXT         NOT NULL,
                    rank    INT          DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   VARCHAR(128) PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id      VARCHAR(36)  PRIMARY KEY,
                    user_id VARCHAR(36)  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name    VARCHAR(256) NOT NULL
                )
            """)
            # Migrate: add approved column if missing
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='users' AND column_name='approved'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT TRUE")
            # Migrate: add group_id column if missing
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='links' AND column_name='group_id'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE links ADD COLUMN group_id VARCHAR(36)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    id         VARCHAR(36)  PRIMARY KEY,
                    user_id    VARCHAR(36)  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash VARCHAR(64)  NOT NULL UNIQUE,
                    name       VARCHAR(256) NOT NULL
                )
            """)
            conn.commit()
            cur.close(); conn.close()
            logger.info("[postgresql] Tables ready.")
        except Exception as e:
            raise RuntimeError(f"[postgresql] Could not create tables: {e}")

    # ── Settings ───────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
        row = cur.fetchone()
        cur.close(); self._release_conn(conn)
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO settings (key, value) VALUES (%s,%s) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (key, value))
        cur.close(); self._release_conn(conn)

    # ── Users ──────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, username, password_hash, is_admin, approved "
                    "FROM users WHERE id=%s AND approved=TRUE", (user_id,))
        row = cur.fetchone()
        cur.close(); self._release_conn(conn)
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, username, password_hash, is_admin, approved "
                    "FROM users WHERE username=%s AND approved=TRUE", (username,))
        row = cur.fetchone()
        cur.close(); self._release_conn(conn)
        return dict(row) if row else None

    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False, approved: bool = True) -> str:
        conn = self._conn()
        cur = conn.cursor()
        user_id = str(uuid.uuid4())
        cur.execute("INSERT INTO users (id, username, password_hash, is_admin, approved) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (user_id, username, password_hash, is_admin, approved))
        cur.close(); self._release_conn(conn)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, username, is_admin, approved FROM users "
                    "WHERE approved=TRUE ORDER BY username")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); self._release_conn(conn)
        return rows

    def delete_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        cur.close(); self._release_conn(conn)

    def set_password(self, user_id: str, password_hash: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (password_hash, user_id))
        cur.close(); self._release_conn(conn)

    def get_pending_users(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, username FROM users WHERE approved=FALSE ORDER BY username")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); self._release_conn(conn)
        return rows

    def approve_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE users SET approved=TRUE WHERE id=%s", (user_id,))
        cur.close(); self._release_conn(conn)

    def reject_user(self, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s AND approved=FALSE", (user_id,))
        cur.close(); self._release_conn(conn)

    # ── Links ──────────────────────────────────────────────────────────────

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, user_id, title, url, rank, group_id FROM links "
                    "WHERE user_id=%s ORDER BY rank", (user_id,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); self._release_conn(conn)
        return rows

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT l.id, l.user_id, u.username, l.title, l.url, l.rank, l.group_id "
                    "FROM links l JOIN users u ON l.user_id=u.id ORDER BY u.username, l.rank")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); self._release_conn(conn)
        return rows

    def add(self, link: Dict[str, Any]) -> str:
        conn = self._conn()
        cur = conn.cursor()
        link_id = str(uuid.uuid4())
        cur.execute("INSERT INTO links (id, user_id, title, url, rank, group_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (link_id, link["user_id"], link["title"], link["url"],
                     link.get("rank", 0), link.get("group_id") or None))
        cur.close(); self._release_conn(conn)
        return link_id

    def delete(self, link_id: str, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM links WHERE id=%s AND user_id=%s", (link_id, user_id))
        cur.close(); self._release_conn(conn)

    def update(self, link_id: str, link: Dict[str, Any], user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE links SET title=%s, url=%s, rank=%s, group_id=%s "
                    "WHERE id=%s AND user_id=%s",
                    (link["title"], link["url"], link.get("rank", 0),
                     link.get("group_id") or None, link_id, user_id))
        cur.close(); self._release_conn(conn)

    # ── Groups ─────────────────────────────────────────────────────────────

    def get_groups(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, user_id, name FROM groups WHERE user_id=%s ORDER BY name", (user_id,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); self._release_conn(conn)
        return rows

    def create_group(self, user_id: str, name: str) -> str:
        conn = self._conn()
        cur = conn.cursor()
        group_id = str(uuid.uuid4())
        cur.execute("INSERT INTO groups (id, user_id, name) VALUES (%s,%s,%s)",
                    (group_id, user_id, name))
        cur.close(); self._release_conn(conn)
        return group_id

    def rename_group(self, group_id: str, user_id: str, name: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE groups SET name=%s WHERE id=%s AND user_id=%s",
                    (name, group_id, user_id))
        cur.close(); self._release_conn(conn)

    def delete_group(self, group_id: str, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM groups WHERE id=%s AND user_id=%s", (group_id, user_id))
        if cur.rowcount:
            cur.execute("UPDATE links SET group_id=NULL WHERE group_id=%s", (group_id,))
        cur.close(); self._release_conn(conn)

    # ── API tokens ─────────────────────────────────────────────────────────

    def create_api_token(self, user_id: str, token_hash: str, name: str) -> str:
        conn = self._conn()
        cur = conn.cursor()
        token_id = str(uuid.uuid4())
        cur.execute("INSERT INTO tokens (id, user_id, token_hash, name) VALUES (%s,%s,%s,%s)",
                    (token_id, user_id, token_hash, name))
        cur.close(); self._release_conn(conn)
        return token_id

    def get_user_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM tokens WHERE token_hash=%s", (token_hash,))
        row = cur.fetchone()
        cur.close(); self._release_conn(conn)
        return self.get_user_by_id(row[0]) if row else None

    def get_api_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, name FROM tokens WHERE user_id=%s ORDER BY name", (user_id,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); self._release_conn(conn)
        return rows

    def revoke_api_token(self, token_id: str, user_id: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM tokens WHERE id=%s AND user_id=%s", (token_id, user_id))
        cur.close(); self._release_conn(conn)
