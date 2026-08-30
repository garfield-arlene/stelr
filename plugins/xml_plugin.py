import os
import uuid
import logging
import xml.etree.ElementTree as ET
import defusedxml.ElementTree as DefusedET
from typing import List, Dict, Any, Optional
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("XML_FILE", "/data/links.xml")


class XmlPlugin(StoragePlugin):
    def __init__(self):
        self._cache = None
        self._cache_mtime = None
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[xml] Creating data directory '{data_dir}'.")
            os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(DATA_FILE):
            logger.info(f"[xml] Creating empty data store '{DATA_FILE}'.")
            root = ET.Element("stelr")
            ET.SubElement(root, "users")
            ET.SubElement(root, "links")
            ET.SubElement(root, "settings")
            ET.SubElement(root, "groups")
            ET.SubElement(root, "tokens")
            self._write(root)
        else:
            try:
                root = DefusedET.parse(DATA_FILE).getroot()
                # Migrate older files
                for tag in ("users", "links", "settings", "groups", "tokens"):
                    if root.find(tag) is None:
                        ET.SubElement(root, tag)
                self._write(root)
                logger.info(f"[xml] Data file '{DATA_FILE}' loaded OK.")
            except ET.ParseError as e:
                raise RuntimeError(f"[xml] Invalid XML in '{DATA_FILE}': {e}")

    def _load(self) -> ET.Element:
        mtime = os.path.getmtime(DATA_FILE)
        if self._cache is not None and self._cache_mtime == mtime:
            return self._cache
        root = DefusedET.parse(DATA_FILE).getroot()
        self._cache = root
        self._cache_mtime = mtime
        return root

    def _write(self, root: ET.Element):
        ET.indent(root, space="  ")
        ET.ElementTree(root).write(DATA_FILE, encoding="unicode", xml_declaration=True)
        self._cache = root
        self._cache_mtime = os.path.getmtime(DATA_FILE)

    # ── Settings ───────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        root = self._load()
        el = root.find(f"settings/{key}")
        return el.text if el is not None and el.text else default

    def set_setting(self, key: str, value: str):
        root = self._load()
        settings = root.find("settings")
        el = settings.find(key)
        if el is None:
            el = ET.SubElement(settings, key)
        el.text = value
        self._write(root)

    # ── Users ──────────────────────────────────────────────────────────────

    def _el_to_user(self, el: ET.Element) -> Dict[str, Any]:
        return {
            "id":            el.get("id"),
            "username":      el.findtext("username", ""),
            "password_hash": el.findtext("password_hash", ""),
            "is_admin":      el.findtext("is_admin", "false") == "true",
            "approved":      el.findtext("approved", "true") == "true",
        }

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        root = self._load()
        for el in root.find("users").findall("user"):
            if el.get("id") == user_id and el.findtext("approved", "true") == "true":
                return self._el_to_user(el)
        return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        root = self._load()
        for el in root.find("users").findall("user"):
            if (el.findtext("username", "") == username
                    and el.findtext("approved", "true") == "true"):
                return self._el_to_user(el)
        return None

    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False, approved: bool = True) -> str:
        root = self._load()
        user_id = str(uuid.uuid4())
        el = ET.SubElement(root.find("users"), "user", id=user_id)
        for key, val in [("username", username), ("password_hash", password_hash),
                         ("is_admin", str(is_admin).lower()),
                         ("approved", str(approved).lower())]:
            ET.SubElement(el, key).text = val
        self._write(root)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._el_to_user(el) for el in root.find("users").findall("user")
                if el.findtext("approved", "true") == "true"]

    def delete_user(self, user_id: str):
        root = self._load()
        users_el = root.find("users")
        for el in users_el.findall("user"):
            if el.get("id") == user_id:
                users_el.remove(el)
                break
        links_el = root.find("links")
        for el in links_el.findall("link"):
            if el.findtext("user_id", "") == user_id:
                links_el.remove(el)
        self._write(root)

    def set_password(self, user_id: str, password_hash: str):
        root = self._load()
        for el in root.find("users").findall("user"):
            if el.get("id") == user_id:
                pw_el = el.find("password_hash")
                if pw_el is None:
                    pw_el = ET.SubElement(el, "password_hash")
                pw_el.text = password_hash
                break
        self._write(root)

    # ── Pending registrations ──────────────────────────────────────────────

    def get_pending_users(self) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._el_to_user(el) for el in root.find("users").findall("user")
                if el.findtext("approved", "true") == "false"]

    def approve_user(self, user_id: str):
        root = self._load()
        for el in root.find("users").findall("user"):
            if el.get("id") == user_id:
                approved_el = el.find("approved")
                if approved_el is None:
                    approved_el = ET.SubElement(el, "approved")
                approved_el.text = "true"
                break
        self._write(root)

    def reject_user(self, user_id: str):
        users_el = self._load().find("users")
        root = self._load()
        users_el = root.find("users")
        for el in users_el.findall("user"):
            if el.get("id") == user_id:
                users_el.remove(el)
                break
        self._write(root)

    # ── Links ──────────────────────────────────────────────────────────────

    def _el_to_link(self, el: ET.Element) -> Dict[str, Any]:
        return {
            "id":       el.get("id"),
            "user_id":  el.findtext("user_id", ""),
            "title":    el.findtext("title", ""),
            "url":      el.findtext("url", ""),
            "rank":     int(el.findtext("rank", "0")),
            "group_id": el.findtext("group_id", ""),
        }

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._el_to_link(el) for el in root.find("links").findall("link")
                if el.findtext("user_id", "") == user_id]

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._el_to_link(el) for el in root.find("links").findall("link")]

    def add(self, link: Dict[str, Any]) -> str:
        root = self._load()
        link_id = str(uuid.uuid4())
        el = ET.SubElement(root.find("links"), "link", id=link_id)
        for key in ("user_id", "title", "url", "rank", "group_id"):
            ET.SubElement(el, key).text = str(link.get(key, ""))
        self._write(root)
        return link_id

    def delete(self, link_id: str, user_id: str):
        root = self._load()
        links_el = root.find("links")
        for el in links_el.findall("link"):
            if el.get("id") == link_id and el.findtext("user_id", "") == user_id:
                links_el.remove(el)
                break
        self._write(root)

    def update(self, link_id: str, link: Dict[str, Any], user_id: str):
        root = self._load()
        for el in root.find("links").findall("link"):
            if el.get("id") == link_id and el.findtext("user_id", "") == user_id:
                for key in ("title", "url", "rank", "group_id"):
                    child = el.find(key)
                    if child is None:
                        child = ET.SubElement(el, key)
                    child.text = str(link.get(key, ""))
                break
        self._write(root)

    # ── Groups ─────────────────────────────────────────────────────────────

    def _el_to_group(self, el: ET.Element) -> Dict[str, Any]:
        return {
            "id":      el.get("id"),
            "user_id": el.findtext("user_id", ""),
            "name":    el.findtext("name", ""),
        }

    def get_groups(self, user_id: str) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._el_to_group(el) for el in root.find("groups").findall("group")
                if el.findtext("user_id", "") == user_id]

    def create_group(self, user_id: str, name: str) -> str:
        root = self._load()
        group_id = str(uuid.uuid4())
        el = ET.SubElement(root.find("groups"), "group", id=group_id)
        ET.SubElement(el, "user_id").text = user_id
        ET.SubElement(el, "name").text = name
        self._write(root)
        return group_id

    def rename_group(self, group_id: str, user_id: str, name: str):
        root = self._load()
        for el in root.find("groups").findall("group"):
            if el.get("id") == group_id and el.findtext("user_id", "") == user_id:
                el.find("name").text = name
                break
        self._write(root)

    def delete_group(self, group_id: str, user_id: str):
        root = self._load()
        groups_el = root.find("groups")
        found = False
        for el in groups_el.findall("group"):
            if el.get("id") == group_id and el.findtext("user_id", "") == user_id:
                groups_el.remove(el)
                found = True
                break
        if found:
            for el in root.find("links").findall("link"):
                if el.findtext("group_id", "") == group_id:
                    el.find("group_id").text = ""
        self._write(root)

    # ── API tokens ─────────────────────────────────────────────────────────

    def create_api_token(self, user_id: str, token_hash: str, name: str) -> str:
        root = self._load()
        token_id = str(uuid.uuid4())
        el = ET.SubElement(root.find("tokens"), "token", id=token_id)
        ET.SubElement(el, "user_id").text = user_id
        ET.SubElement(el, "token_hash").text = token_hash
        ET.SubElement(el, "name").text = name
        self._write(root)
        return token_id

    def get_user_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        root = self._load()
        for el in root.find("tokens").findall("token"):
            if el.findtext("token_hash", "") == token_hash:
                return self.get_user_by_id(el.findtext("user_id", ""))
        return None

    def get_api_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        root = self._load()
        return [{"id": el.get("id"), "name": el.findtext("name", "")}
                for el in root.find("tokens").findall("token")
                if el.findtext("user_id", "") == user_id]

    def revoke_api_token(self, token_id: str, user_id: str):
        root = self._load()
        tokens_el = root.find("tokens")
        for el in tokens_el.findall("token"):
            if el.get("id") == token_id and el.findtext("user_id", "") == user_id:
                tokens_el.remove(el)
                break
        self._write(root)
