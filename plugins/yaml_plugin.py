import os
import uuid
import logging
import yaml
from typing import List, Dict, Any, Optional
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("YAML_FILE", "/data/links.yaml")


class YamlPlugin(StoragePlugin):
    def __init__(self):
        self._cache = None
        self._cache_mtime = None
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[yaml] Creating data directory '{data_dir}'.")
            os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(DATA_FILE):
            logger.info(f"[yaml] Creating empty data store '{DATA_FILE}'.")
            self._write({"users": [], "links": [], "settings": {}, "groups": []})
        else:
            try:
                data = self._load()
                if not isinstance(data, dict):
                    raise RuntimeError(f"[yaml] '{DATA_FILE}' must be a YAML mapping.")
                # Migrate older files missing new keys
                dirty = False
                for key in ("users", "links", "settings", "groups"):
                    if key not in data:
                        data[key] = [] if key != "settings" else {}
                        dirty = True
                if dirty:
                    self._write(data)
                logger.info(f"[yaml] Data file '{DATA_FILE}' loaded OK.")
            except yaml.YAMLError as e:
                raise RuntimeError(f"[yaml] Invalid YAML in '{DATA_FILE}': {e}")

    def _load(self) -> Dict:
        mtime = os.path.getmtime(DATA_FILE)
        if self._cache is not None and self._cache_mtime == mtime:
            return self._cache
        with open(DATA_FILE, "r") as f:
            data = yaml.safe_load(f)
        if not data:
            data = {"users": [], "links": [], "settings": {}, "groups": []}
        data.setdefault("users", [])
        data.setdefault("links", [])
        data.setdefault("settings", {})
        data.setdefault("groups", [])
        self._cache = data
        self._cache_mtime = mtime
        return data

    def _write(self, data: Dict):
        with open(DATA_FILE, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        self._cache = data
        self._cache_mtime = os.path.getmtime(DATA_FILE)

    # ── Settings ───────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        return str(self._load()["settings"].get(key, default))

    def set_setting(self, key: str, value: str):
        data = self._load()
        data["settings"][key] = value
        self._write(data)

    # ── Users ──────────────────────────────────────────────────────────────

    def _approved(self, u: Dict) -> bool:
        return u.get("approved", True)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._load()["users"]
                     if u.get("id") == user_id and self._approved(u)), None)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._load()["users"]
                     if u.get("username") == username and self._approved(u)), None)

    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False, approved: bool = True) -> str:
        data = self._load()
        user_id = str(uuid.uuid4())
        data["users"].append({
            "id": user_id, "username": username,
            "password_hash": password_hash,
            "is_admin": is_admin, "approved": approved,
        })
        self._write(data)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        return [u for u in self._load()["users"] if self._approved(u)]

    def delete_user(self, user_id: str):
        data = self._load()
        data["users"] = [u for u in data["users"] if u.get("id") != user_id]
        data["links"] = [l for l in data["links"] if l.get("user_id") != user_id]
        self._write(data)

    def set_password(self, user_id: str, password_hash: str):
        data = self._load()
        for u in data["users"]:
            if u.get("id") == user_id:
                u["password_hash"] = password_hash
                break
        self._write(data)

    # ── Pending registrations ──────────────────────────────────────────────

    def get_pending_users(self) -> List[Dict[str, Any]]:
        return [u for u in self._load()["users"] if not self._approved(u)]

    def approve_user(self, user_id: str):
        data = self._load()
        for u in data["users"]:
            if u.get("id") == user_id:
                u["approved"] = True
                break
        self._write(data)

    def reject_user(self, user_id: str):
        data = self._load()
        data["users"] = [u for u in data["users"] if u.get("id") != user_id]
        self._write(data)

    # ── Links ──────────────────────────────────────────────────────────────

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        return [l for l in self._load()["links"] if l.get("user_id") == user_id]

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        return self._load()["links"]

    def add(self, link: Dict[str, Any]) -> str:
        data = self._load()
        link_id = str(uuid.uuid4())
        data["links"].append({"id": link_id, **link})
        self._write(data)
        return link_id

    def delete(self, link_id: str, user_id: str):
        data = self._load()
        data["links"] = [l for l in data["links"]
                         if not (l.get("id") == link_id and l.get("user_id") == user_id)]
        self._write(data)

    def update(self, link_id: str, link: Dict[str, Any], user_id: str):
        data = self._load()
        for l in data["links"]:
            if l.get("id") == link_id and l.get("user_id") == user_id:
                l.update(link)
                break
        self._write(data)

    # ── Groups ─────────────────────────────────────────────────────────────

    def get_groups(self, user_id: str) -> List[Dict[str, Any]]:
        return [g for g in self._load()["groups"] if g.get("user_id") == user_id]

    def create_group(self, user_id: str, name: str) -> str:
        data = self._load()
        group_id = str(uuid.uuid4())
        data["groups"].append({"id": group_id, "user_id": user_id, "name": name})
        self._write(data)
        return group_id

    def rename_group(self, group_id: str, user_id: str, name: str):
        data = self._load()
        for g in data["groups"]:
            if g.get("id") == group_id and g.get("user_id") == user_id:
                g["name"] = name
                break
        self._write(data)

    def delete_group(self, group_id: str, user_id: str):
        data = self._load()
        remaining = [g for g in data["groups"]
                     if not (g.get("id") == group_id and g.get("user_id") == user_id)]
        if len(remaining) != len(data["groups"]):
            for l in data["links"]:
                if l.get("group_id") == group_id:
                    l["group_id"] = ""
        data["groups"] = remaining
        self._write(data)
