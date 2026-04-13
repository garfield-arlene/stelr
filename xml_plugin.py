import os
import uuid
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("XML_FILE", "/data/links.xml")


class XmlPlugin(StoragePlugin):
    def __init__(self):
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[xml] Data directory '{data_dir}' not found — creating.")
            os.makedirs(data_dir, exist_ok=True)

        if not os.path.exists(DATA_FILE):
            logger.info(f"[xml] Data file '{DATA_FILE}' not found — creating empty store.")
            root = ET.Element("links")
            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ")
            tree.write(DATA_FILE, encoding="unicode", xml_declaration=True)
        else:
            # Validate the file is parseable
            try:
                ET.parse(DATA_FILE)
                logger.info(f"[xml] Existing data file '{DATA_FILE}' loaded OK.")
            except ET.ParseError as e:
                raise RuntimeError(
                    f"[xml] Data file '{DATA_FILE}' exists but is not valid XML: {e}"
                )

    def _load(self) -> ET.Element:
        return ET.parse(DATA_FILE).getroot()

    def _save(self, root: ET.Element):
        ET.indent(root, space="  ")
        ET.ElementTree(root).write(DATA_FILE, encoding="unicode", xml_declaration=True)

    def get_all(self) -> List[Dict[str, Any]]:
        root = self._load()
        return [
            {
                "id":    el.get("id"),
                "title": el.findtext("title", ""),
                "url":   el.findtext("url", ""),
                "rank":  int(el.findtext("rank", "0")),
            }
            for el in root.findall("link")
        ]

    def add(self, link: Dict[str, Any]) -> str:
        root = self._load()
        link_id = str(uuid.uuid4())
        el = ET.SubElement(root, "link", id=link_id)
        for key in ("title", "url", "rank"):
            child = ET.SubElement(el, key)
            child.text = str(link.get(key, ""))
        self._save(root)
        return link_id

    def delete(self, link_id: str):
        root = self._load()
        for el in root.findall("link"):
            if el.get("id") == link_id:
                root.remove(el)
                break
        self._save(root)

    def update(self, link_id: str, link: Dict[str, Any]):
        root = self._load()
        for el in root.findall("link"):
            if el.get("id") == link_id:
                for key in ("title", "url", "rank"):
                    child = el.find(key)
                    if child is None:
                        child = ET.SubElement(el, key)
                    child.text = str(link.get(key, ""))
                break
        self._save(root)
