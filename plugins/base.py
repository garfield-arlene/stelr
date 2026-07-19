from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class StoragePlugin(ABC):

    # ── Links ──────────────────────────────────────────────────────────────

    @abstractmethod
    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all links for a given user, sorted by rank."""

    @abstractmethod
    def add(self, link: Dict[str, Any]) -> str:
        """Add a link (must include user_id) and return its generated id."""

    @abstractmethod
    def delete(self, link_id: str, user_id: str) -> None:
        """Delete a link by id, scoped to user."""

    @abstractmethod
    def update(self, link_id: str, link: Dict[str, Any], user_id: str) -> None:
        """Update a link by id, scoped to user."""

    @abstractmethod
    def get_all_links_admin(self) -> List[Dict[str, Any]]:
        """Return all links for all users (admin only)."""

    # ── Users ──────────────────────────────────────────────────────────────

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return a user dict or None. Only returns approved/admin users."""

    @abstractmethod
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Return a user dict or None. Only returns approved/admin users."""

    @abstractmethod
    def create_user(self, username: str, password_hash: str,
                    is_admin: bool = False, approved: bool = True) -> str:
        """Create a user and return their generated id."""

    @abstractmethod
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Return all approved (non-pending) users (admin only)."""

    @abstractmethod
    def delete_user(self, user_id: str) -> None:
        """Delete a user and all their links."""

    @abstractmethod
    def set_password(self, user_id: str, password_hash: str) -> None:
        """Set a user's password hash."""

    # ── Pending registrations ──────────────────────────────────────────────

    @abstractmethod
    def get_pending_users(self) -> List[Dict[str, Any]]:
        """Return all users awaiting approval."""

    @abstractmethod
    def approve_user(self, user_id: str) -> None:
        """Mark a pending user as approved."""

    @abstractmethod
    def reject_user(self, user_id: str) -> None:
        """Delete a pending user registration."""

    # ── Settings ───────────────────────────────────────────────────────────

    @abstractmethod
    def get_setting(self, key: str, default: str = "") -> str:
        """Return a stored setting value."""

    @abstractmethod
    def set_setting(self, key: str, value: str) -> None:
        """Store a setting value."""

    # ── Groups ─────────────────────────────────────────────────────────────

    @abstractmethod
    def get_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all groups belonging to a user."""

    @abstractmethod
    def create_group(self, user_id: str, name: str) -> str:
        """Create a group for a user and return its generated id."""

    @abstractmethod
    def rename_group(self, group_id: str, user_id: str, name: str) -> None:
        """Rename a group, scoped to user."""

    @abstractmethod
    def delete_group(self, group_id: str, user_id: str) -> None:
        """Delete a group, scoped to user. Its links become ungrouped."""

    # ── API tokens ─────────────────────────────────────────────────────────

    @abstractmethod
    def create_api_token(self, user_id: str, token_hash: str, name: str) -> str:
        """Store a new API token (given its hash) for a user and return its generated id."""

    @abstractmethod
    def get_user_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Return the user dict owning this token hash, or None if unknown/revoked."""

    @abstractmethod
    def get_api_tokens(self, user_id: str) -> List[Dict[str, Any]]:
        """Return a user's tokens (id + name only, never the hash)."""

    @abstractmethod
    def revoke_api_token(self, token_id: str, user_id: str) -> None:
        """Delete a token by id, scoped to owner."""
