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
<script id="stelr-settings" type="application/json">{}</script>
<script id="stelr-groups" type="application/json">[]</script>
<script id="stelr-tokens" type="application/json">[]</script>
<ul id="links"></ul>
</body>
</html>"""


class HtmlPlugin(StoragePlugin):
    def __init__(self):
        self._cache = None
        self._cache_mtime = None
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
            soup = self._load()
            dirty = False
            if not soup.find("script", id="stelr-settings"):
                tag = soup.new_tag("script", id="stelr-settings", type="application/json")
                tag.string = "{}"
                soup.body.insert(1, tag)
                dirty = True
            if not soup.find("script", id="stelr-groups"):
                tag = soup.new_tag("script", id="stelr-groups", type="application/json")
                tag.string = "[]"
                soup.body.insert(2, tag)
                dirty = True
            if not soup.find("script", id="stelr-tokens"):
                tag = soup.new_tag("script", id="stelr-tokens", type="application/json")
                tag.string = "[]"
                soup.body.insert(3, tag)
                dirty = True
            if dirty:
                self._save(soup)
            logger.info(f"[html] Data file '{DATA_FILE}' loaded OK.")

    def _load(self) -> BeautifulSoup:
        mtime = os.path.getmtime(DATA_FILE)
        if self._cache is not None and self._cache_mtime == mtime:
            return self._cache
        with open(DATA_FILE, "r") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        self._cache = soup
        self._cache_mtime = mtime
        return soup

    def _save(self, soup: BeautifulSoup):
        with open(DATA_FILE, "w") as f:
            f.write(soup.prettify())
        self._cache = soup
        self._cache_mtime = os.path.getmtime(DATA_FILE)

    # ── Settings ───────────────────────────────────────────────────────────

    def _get_settings(self, soup: BeautifulSoup) -> Dict:
        tag = soup.find("script", id="stelr-settings")
        return json.loads(tag.string or "{}") if tag else {}

    def _set_settings(self, soup: BeautifulSoup, settings: Dict):
        tag = soup.find("script", id="stelr-settings")
        if not tag:
            tag = soup.new_tag("script", id="stelr-settings", type="application/json")
            soup.body.insert(1, tag)
        tag.string = json.dumps(settings)

    def get_setting(self, key: str, default: str = "") -> str:
        return str(self._get_settings(self._load()).get(key, default))

    def set_setting(self, key: str, value: str):
        soup = self._load()
        settings = self._get_settings(soup)
        settings[key] = value
        self._set_settings(soup, settings)
        self._save(soup)

    # ── Users ──────────────────────────────────────────────────────────────

    def _get_users(self, soup: BeautifulSoup) -> List[Dict]:
        tag = soup.find("script", id="stelr-users")
        return json.loads(tag.string or "[]") if tag else []

    def _set_users(self, soup: BeautifulSoup, users: List[Dict]):
        tag = soup.find("script", id="stelr-users")
        if not tag:
            tag = soup.new_tag("script", id="stelr-users", type="application/json")
            soup.body.insert(0, tag)
        tag.string = json.dumps(users)

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._get_users(self._load())
                     if u.get("id") == user_id and u.get("approved", True)), None)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._get_users(self._load())
                     if u.get("username") == username and u.get("approved", True)), None)

    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False, approved: bool = True) -> str:
        soup = self._load()
        users = self._get_users(soup)
        user_id = str(uuid.uuid4())
        users.append({"id": user_id, "username": username,
                       "password_hash": password_hash,
                       "is_admin": is_admin, "approved": approved})
        self._set_users(soup, users)
        self._save(soup)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        return [u for u in self._get_users(self._load()) if u.get("approved", True)]

    def delete_user(self, user_id: str):
        soup = self._load()
        self._set_users(soup, [u for u in self._get_users(soup) if u.get("id") != user_id])
        for li in soup.select(f"li[data-user-id='{user_id}']"):
            li.decompose()
        self._save(soup)

    def set_password(self, user_id: str, password_hash: str):
        soup = self._load()
        users = self._get_users(soup)
        for u in users:
            if u.get("id") == user_id:
                u["password_hash"] = password_hash
                break
        self._set_users(soup, users)
        self._save(soup)

    def get_pending_users(self) -> List[Dict[str, Any]]:
        return [u for u in self._get_users(self._load()) if not u.get("approved", True)]

    def approve_user(self, user_id: str):
        soup = self._load()
        users = self._get_users(soup)
        for u in users:
            if u.get("id") == user_id:
                u["approved"] = True
                break
        self._set_users(soup, users)
        self._save(soup)

    def reject_user(self, user_id: str):
        soup = self._load()
        self._set_users(soup, [u for u in self._get_users(soup) if u.get("id") != user_id])
        self._save(soup)

    # ── Links ──────────────────────────────────────────────────────────────

    def _li_to_dict(self, li) -> Dict[str, Any]:
        return {
            "id":       li.get("data-id", ""),
            "user_id":  li.get("data-user-id", ""),
            "title":    li.get("data-title", ""),
            "url":      li.get("data-url", ""),
            "rank":     int(li.get("data-rank", "0")),
            "group_id": li.get("data-group-id", ""),
        }

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        return [self._li_to_dict(li) for li in self._load().select("ul#links > li")
                if li.get("data-user-id") == user_id]

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        return [self._li_to_dict(li) for li in self._load().select("ul#links > li")]

    def add(self, link: Dict[str, Any]) -> str:
        soup = self._load()
        link_id = str(uuid.uuid4())
        ul = soup.find("ul", id="links")
        li = soup.new_tag("li", attrs={
            "data-id": link_id, "data-user-id": link.get("user_id", ""),
            "data-title": link.get("title", ""), "data-url": link.get("url", ""),
            "data-rank": str(link.get("rank", 0)),
            "data-group-id": link.get("group_id", ""),
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
                li["data-title"]    = link.get("title", "")
                li["data-url"]      = link.get("url", "")
                li["data-rank"]     = str(link.get("rank", 0))
                li["data-group-id"] = link.get("group_id", "")
                a = li.find("a")
                if a:
                    a["href"] = link.get("url", "")
                    a.string  = link.get("title", "")
        self._save(soup)

    # ── Groups ─────────────────────────────────────────────────────────────

    def _get_groups(self, soup: BeautifulSoup) -> List[Dict]:
        tag = soup.find("script", id="stelr-groups")
        return json.loads(tag.string or "[]") if tag else []

    def _set_groups(self, soup: BeautifulSoup, groups: List[Dict]):
        tag = soup.find("script", id="stelr-groups")
        if not tag:
            tag = soup.new_tag("script", id="stelr-groups", type="application/json")
            soup.body.insert(0, tag)
        tag.string = json.dumps(groups)

    def get_groups(self, user_id: str) -> List[Dict[str, Any]]:
        return [g for g in self._get_groups(self._load()) if g.get("user_id") == user_id]

    def create_group(self, user_id: str, name: str) -> str:
        soup = self._load()
        groups = self._get_groups(soup)
        group_id = str(uuid.uuid4())
        groups.append({"id": group_id, "user_id": user_id, "name": name})
        self._set_groups(soup, groups)
        self._save(soup)
        return group_id

    def rename_group(self, group_id: str, user_id: str, name: str):
        soup = self._load()
        groups = self._get_groups(soup)
        for g in groups:
            if g.get("id") == group_id and g.get("user_id") == user_id:
                g["name"] = name
                break
        self._set_groups(soup, groups)
        self._save(soup)

    def delete_group(self, group_id: str, user_id: str):
        soup = self._load()
        groups = self._get_groups(soup)
        remaining = [g for g in groups if not (g.get("id") == group_id and g.get("user_id") == user_id)]
        if len(remaining) != len(groups):
            for li in soup.select(f"li[data-group-id='{group_id}']"):
                li["data-group-id"] = ""
        self._set_groups(soup, remaining)
        self._save(soup)

    # ── API tokens ─────────────────────────────────────────────────────────

    def _get_tokens(self, soup: BeautifulSoup) -> List[Dict]:
        tag = soup.find("script", id="stelr-tokens")
        return json.loads(tag.string or "[]") if tag else []

    def _set_tokens(self, soup: BeautifulSoup, tokens: List[Dict]):
        tag = soup.find("script", id="stelr-tokens")
        if not tag:
            tag = soup.new_tag("script", id="stelr-tokens", type="application/json")
            soup.body.insert(0, tag)
        tag.string = json.dumps(tokens)

    def create_api_token(self, user_id: str, token_hash: str, name: str) -> str:
        soup = self._load()
        tokens = self._get_tokens(soup)
        token_id = str(uuid.uuid4())
        tokens.append({"id": token_id, "user_id": user_id,
                        "token_hash": token_hash, "name": name})
        self._set_tokens(soup, tokens)
        self._save(soup)
        return token_id

    def get_user_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        token = next((t for t in self._get_tokens(self._load())
                      if t.get("token_hash") == token_hash), None)
        return self.get_user_by_id(token["user_id"]) if token else None

    def get_api_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        return [{"id": t["id"], "name": t.get("name", "")}
                for t in self._get_tokens(self._load()) if t.get("user_id") == user_id]

    def revoke_api_token(self, token_id: str, user_id: str):
        soup = self._load()
        tokens = self._get_tokens(soup)
        self._set_tokens(soup, [t for t in tokens
                                if not (t.get("id") == token_id and t.get("user_id") == user_id)])
        self._save(soup)
