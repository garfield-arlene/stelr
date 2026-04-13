import os
import uuid
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("HTML_FILE", "/data/links.html")

TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Stelr Data</title></head>
<body>
<ul id="links">
</ul>
</body>
</html>"""


class HtmlPlugin(StoragePlugin):
    def __init__(self):
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[html] Data directory '{data_dir}' not found — creating.")
            os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(DATA_FILE):
            logger.info(f"[html] Data file '{DATA_FILE}' not found — creating empty store.")
            with open(DATA_FILE, "w") as f:
                f.write(TEMPLATE)
        else:
            try:
                with open(DATA_FILE, "r") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")
                if not soup.find("ul", id="links"):
                    raise RuntimeError(
                        f"[html] Data file '{DATA_FILE}' is missing <ul id=\"links\">.")
                count = len(soup.select("ul#links > li"))
                logger.info(f"[html] Existing data file '{DATA_FILE}' loaded OK ({count} entries).")
            except Exception as e:
                raise RuntimeError(f"[html] Data file '{DATA_FILE}' could not be parsed: {e}")

    def _load(self) -> BeautifulSoup:
        with open(DATA_FILE, "r") as f:
            return BeautifulSoup(f.read(), "html.parser")

    def _save(self, soup: BeautifulSoup):
        with open(DATA_FILE, "w") as f:
            f.write(soup.prettify())

    def get_all(self) -> List[Dict[str, Any]]:
        soup = self._load()
        return [
            {
                "id":    li.get("data-id", ""),
                "title": li.get("data-title", ""),
                "url":   li.get("data-url", ""),
                "rank":  int(li.get("data-rank", "0")),
            }
            for li in soup.select("ul#links > li")
        ]

    def add(self, link: Dict[str, Any]) -> str:
        soup = self._load()
        link_id = str(uuid.uuid4())
        ul = soup.find("ul", id="links")
        li = soup.new_tag("li", attrs={
            "data-id":    link_id,
            "data-title": link.get("title", ""),
            "data-url":   link.get("url", ""),
            "data-rank":  str(link.get("rank", 0)),
        })
        a = soup.new_tag("a", href=link.get("url", ""))
        a.string = link.get("title", "")
        li.append(a)
        ul.append(li)
        self._save(soup)
        return link_id

    def delete(self, link_id: str):
        soup = self._load()
        for li in soup.select(f"li[data-id='{link_id}']"):
            li.decompose()
        self._save(soup)

    def update(self, link_id: str, link: Dict[str, Any]):
        soup = self._load()
        for li in soup.select(f"li[data-id='{link_id}']"):
            li["data-title"] = link.get("title", "")
            li["data-url"]   = link.get("url", "")
            li["data-rank"]  = str(link.get("rank", 0))
            a = li.find("a")
            if a:
                a["href"] = link.get("url", "")
                a.string  = link.get("title", "")
        self._save(soup)
