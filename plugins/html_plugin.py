import os
import uuid
import json
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("HTML_FILE", "/data/links.html")

TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Stelr Data</title></head>
<body>
<script id="stelr-users" type="application/json">[]</script>
<ul id="links"></ul>
</body>
</html>"""


class HtmlPlugin(StoragePlugin):
    def __init__(self):
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[html] Creating data directory '{data_dir}'.")
            os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(DATA_FILE):
            logger.info(f"[html] Creating empty data store '{DATA_FILE}'.")
            with open(DATA_FILE, "w") as f:
                f.write(TEMPLATE)
        else:
            with open(DATA_FILE, "r") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            if not soup.find("ul", id="links"):
                raise RuntimeError(f"[html] '{DATA_FILE}' missing <ul id='links'>.")
            logger.info(f"[html] Data file '{DATA_FILE}' loaded OK.")

    def _load(self) -> BeautifulSoup:
        with open(DATA_FILE, "r") as f:
            return BeautifulSoup(f.read(), "html.parser")

    def _save(self, soup: BeautifulSoup):
        with open(DATA_FILE, "w") as f:
            f.write(soup.prettify())

    # ── Users ──────────────────────────────────────────────────────────────

    def _get_users(self, soup: BeautifulSoup) -> List[Dict]:
        tag = soup.find("script", id="stelr-users")
        if not tag:
            return []
        return json.loads(tag.string or "[]")

    def _set_users(self, soup: BeautifulSoup, users: List[Dict]):
        tag = soup.find("script", id="stelr-users")
        if not tag:
            tag = soup.new_tag("script", id="stelr-users", type="application/json")
            soup.body.insert(0, tag)
        tag.string = json.dumps(users)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._get_users(self._load()) if u.get("id") == user_id), None)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._get_users(self._load()) if u.get("username") == username), None)

    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> str:
        soup = self._load()
        users = self._get_users(soup)
        user_id = str(uuid.uuid4())
        users.append({"id": user_id, "username": username,
                       "password_hash": password_hash, "is_admin": is_admin})
        self._set_users(soup, users)
        self._save(soup)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        return self._get_users(self._load())

    def delete_user(self, user_id: str):
        soup = self._load()
        users = [u for u in self._get_users(soup) if u.get("id") != user_id]
        self._set_users(soup, users)
        for li in soup.select(f"li[data-user-id='{user_id}']"):
            li.decompose()
        self._save(soup)

    # ── Links ──────────────────────────────────────────────────────────────

    def _li_to_dict(self, li) -> Dict[str, Any]:
        return {
            "id":      li.get("data-id", ""),
            "user_id": li.get("data-user-id", ""),
            "title":   li.get("data-title", ""),
            "url":     li.get("data-url", ""),
            "rank":    int(li.get("data-rank", "0")),
        }

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        soup = self._load()
        return [self._li_to_dict(li) for li in soup.select("ul#links > li")
                if li.get("data-user-id") == user_id]

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        soup = self._load()
        return [self._li_to_dict(li) for li in soup.select("ul#links > li")]

    def add(self, link: Dict[str, Any]) -> str:
        soup = self._load()
        link_id = str(uuid.uuid4())
        ul = soup.find("ul", id="links")
        li = soup.new_tag("li", attrs={
            "data-id":      link_id,
            "data-user-id": link.get("user_id", ""),
            "data-title":   link.get("title", ""),
            "data-url":     link.get("url", ""),
            "data-rank":    str(link.get("rank", 0)),
        })
        a = soup.new_tag("a", href=link.get("url", ""))
        a.string = link.get("title", "")
        li.append(a)
        ul.append(li)
        self._save(soup)
        return link_id

    def delete(self, link_id: str, user_id: str):
        soup = self._load()
        for li in soup.select(f"li[data-id='{link_id}']"):
            if li.get("data-user-id") == user_id:
                li.decompose()
        self._save(soup)

    def update(self, link_id: str, link: Dict[str, Any], user_id: str):
        soup = self._load()
        for li in soup.select(f"li[data-id='{link_id}']"):
            if li.get("data-user-id") == user_id:
                li["data-title"] = link.get("title", "")
                li["data-url"]   = link.get("url", "")
                li["data-rank"]  = str(link.get("rank", 0))
                a = li.find("a")
                if a:
                    a["href"] = link.get("url", "")
                    a.string  = link.get("title", "")
        self._save(soup)
