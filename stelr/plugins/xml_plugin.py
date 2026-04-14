import os
import uuid
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("XML_FILE", "/data/links.xml")


class XmlPlugin(StoragePlugin):
    def __init__(self):
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
            self._write(root)
        else:
            try:
                ET.parse(DATA_FILE)
                logger.info(f"[xml] Data file '{DATA_FILE}' loaded OK.")
            except ET.ParseError as e:
                raise RuntimeError(f"[xml] Invalid XML in '{DATA_FILE}': {e}")

    def _load(self) -> ET.Element:
        return ET.parse(DATA_FILE).getroot()

    def _write(self, root: ET.Element):
        ET.indent(root, space="  ")
        ET.ElementTree(root).write(DATA_FILE, encoding="unicode", xml_declaration=True)

    # ── Users ──────────────────────────────────────────────────────────────

    def _user_to_dict(self, el: ET.Element) -> Dict[str, Any]:
        return {
            "id":            el.get("id"),
            "username":      el.findtext("username", ""),
            "password_hash": el.findtext("password_hash", ""),
            "is_admin":      el.findtext("is_admin", "false") == "true",
        }

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        root = self._load()
        for el in root.find("users").findall("user"):
            if el.get("id") == user_id:
                return self._user_to_dict(el)
        return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        root = self._load()
        for el in root.find("users").findall("user"):
            if el.findtext("username", "") == username:
                return self._user_to_dict(el)
        return None

    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> str:
        root = self._load()
        user_id = str(uuid.uuid4())
        el = ET.SubElement(root.find("users"), "user", id=user_id)
        for key, val in [("username", username), ("password_hash", password_hash),
                         ("is_admin", str(is_admin).lower())]:
            child = ET.SubElement(el, key)
            child.text = val
        self._write(root)
        return user_id

    def get_all_users(self) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._user_to_dict(el) for el in root.find("users").findall("user")]

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

    # ── Links ──────────────────────────────────────────────────────────────

    def _link_to_dict(self, el: ET.Element) -> Dict[str, Any]:
        return {
            "id":      el.get("id"),
            "user_id": el.findtext("user_id", ""),
            "title":   el.findtext("title", ""),
            "url":     el.findtext("url", ""),
            "rank":    int(el.findtext("rank", "0")),
        }

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._link_to_dict(el) for el in root.find("links").findall("link")
                if el.findtext("user_id", "") == user_id]

    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        root = self._load()
        return [self._link_to_dict(el) for el in root.find("links").findall("link")]

    def add(self, link: Dict[str, Any]) -> str:
        root = self._load()
        link_id = str(uuid.uuid4())
        el = ET.SubElement(root.find("links"), "link", id=link_id)
        for key in ("user_id", "title", "url", "rank"):
            child = ET.SubElement(el, key)
            child.text = str(link.get(key, ""))
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
                for key in ("title", "url", "rank"):
                    child = el.find(key)
                    if child is None:
                        child = ET.SubElement(el, key)
                    child.text = str(link.get(key, ""))
                break
        self._write(root)
