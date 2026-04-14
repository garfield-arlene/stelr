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
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[yaml] Creating data directory '{data_dir}'.")
            os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(DATA_FILE):
            logger.info(f"[yaml] Creating empty data store '{DATA_FILE}'.")
            self._write({"users": [], "links": []})
        else:
            try:
                data = self._load()
                if not isinstance(data, dict):
                    raise RuntimeError(f"[yaml] '{DATA_FILE}' must be a YAML mapping.")
                logger.info(f"[yaml] Data file '{DATA_FILE}' loaded OK.")
            except yaml.YAMLError as e:
                raise RuntimeError(f"[yaml] Invalid YAML in '{DATA_FILE}': {e}")

    def _load(self) -> Dict:
        with open(DATA_FILE, "r") as f:
            data = yaml.safe_load(f)
        if not data:
            return {"users": [], "links": []}
        data.setdefault("users", [])
        data.setdefault("links", [])
        return data

    def _write(self, data: Dict):
        with open(DATA_FILE, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    # ── Users ──────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._load()["users"] if u.get("id") == user_id), None)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._load()["users"] if u.get("username") == username), None)

    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> str:
        data = self._load()
        user_id = str(uuid.uuid4())
        data["users"].append({"id": user_id, "username": username,
                               "password_hash": password_hash, "is_admin": is_admin})
        self._write(data)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        return self._load()["users"]

    def delete_user(self, user_id: str):
        data = self._load()
        data["users"] = [u for u in data["users"] if u.get("id") != user_id]
        data["links"] = [l for l in data["links"] if l.get("user_id") != user_id]
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
