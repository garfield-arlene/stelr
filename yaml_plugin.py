import os
import uuid
import logging
import yaml
from typing import List, Dict, Any
from plugins.base import StoragePlugin

logger = logging.getLogger(__name__)

DATA_FILE = os.environ.get("YAML_FILE", "/data/links.yaml")


class YamlPlugin(StoragePlugin):
    def __init__(self):
        self._bootstrap()

    def _bootstrap(self):
        data_dir = os.path.dirname(DATA_FILE)
        if not os.path.exists(data_dir):
            logger.info(f"[yaml] Data directory '{data_dir}' not found — creating.")
            os.makedirs(data_dir, exist_ok=True)

        if not os.path.exists(DATA_FILE):
            logger.info(f"[yaml] Data file '{DATA_FILE}' not found — creating empty store.")
            self._save([])
        else:
            # Validate the file is parseable
            try:
                with open(DATA_FILE, "r") as f:
                    data = yaml.safe_load(f)
                if data is not None and not isinstance(data, list):
                    raise RuntimeError(
                        f"[yaml] Data file '{DATA_FILE}' exists but does not contain a list."
                    )
                logger.info(f"[yaml] Existing data file '{DATA_FILE}' loaded OK "
                            f"({len(data) if data else 0} entries).")
            except yaml.YAMLError as e:
                raise RuntimeError(
                    f"[yaml] Data file '{DATA_FILE}' exists but is not valid YAML: {e}"
                )

    def _load(self) -> List[Dict]:
        with open(DATA_FILE, "r") as f:
            data = yaml.safe_load(f)
        return data if data else []

    def _save(self, links: List[Dict]):
        with open(DATA_FILE, "w") as f:
            yaml.dump(links, f, default_flow_style=False, allow_unicode=True)

    def get_all(self) -> List[Dict[str, Any]]:
        return self._load()

    def add(self, link: Dict[str, Any]) -> str:
        links = self._load()
        link_id = str(uuid.uuid4())
        links.append({"id": link_id, **link})
        self._save(links)
        return link_id

    def delete(self, link_id: str):
        links = [l for l in self._load() if l.get("id") != link_id]
        self._save(links)

    def update(self, link_id: str, link: Dict[str, Any]):
        links = self._load()
        for l in links:
            if l.get("id") == link_id:
                l.update(link)
                break
        self._save(links)
