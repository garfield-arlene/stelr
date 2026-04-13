from abc import ABC, abstractmethod
from typing import List, Dict, Any

class StoragePlugin(ABC):
    @abstractmethod
    def get_all(self) -> List[Dict[str, Any]]:
        """Return all links as a list of dicts with keys: id, title, url, rank"""

    @abstractmethod
    def add(self, link: Dict[str, Any]) -> str:
        """Add a link and return its generated id"""

    @abstractmethod
    def delete(self, link_id: str) -> None:
        """Delete a link by id"""

    @abstractmethod
    def update(self, link_id: str, link: Dict[str, Any]) -> None:
        """Update an existing link by id"""
