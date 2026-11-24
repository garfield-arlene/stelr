import math
import operator
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import List, Dict, Any, Optional, Tuple


# ── Link queries (filter, sort, paginate) ──────────────────────────────────

RANK_OPS = {
    "<":  operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    ">=": operator.ge,
    ">":  operator.gt,
}
SORT_FIELDS = ("rank", "title", "url")
UNGROUPED = "__ungrouped__"


@dataclass(frozen=True)
class LinkQuery:
    """What to show from a user's links. Built with LinkQuery.build so every
    field is already validated; backends can trust it."""
    q: str = ""
    rank_op: str = ""            # a key of RANK_OPS, or "" for no rank filter
    rank_val: Optional[int] = None
    group: str = ""              # "", UNGROUPED, or a group id
    sort: str = "rank"
    direction: str = "asc"
    page: int = 1
    per_page: Optional[int] = None   # None means every matching link
    # The dashboard moves a too-high page back to the last one; the API
    # leaves it alone so clients paging "until empty" do stop.
    clamp_page: bool = True

    @classmethod
    def build(cls, q="", rank_op="", rank_val="", group="", sort="rank",
              direction="asc", page=1, per_page=None,
              clamp_page=True) -> "LinkQuery":
        try:
            rank_int = int(str(rank_val).strip())
        except (TypeError, ValueError):
            rank_int = None
        if rank_op not in RANK_OPS or rank_int is None:
            rank_op, rank_int = "", None
        try:
            page = max(1, int(page))
        except (TypeError, ValueError):
            page = 1
        if per_page is not None and per_page < 1:
            per_page = None
        return cls(q=(q or "").strip(), rank_op=rank_op, rank_val=rank_int,
                   group=(group or "").strip(),
                   sort=sort if sort in SORT_FIELDS else "rank",
                   direction=direction if direction in ("asc", "desc") else "asc",
                   page=page, per_page=per_page, clamp_page=clamp_page)

    def clamp(self, total: int) -> "LinkQuery":
        """Move page back inside range once the total is known."""
        if not self.per_page:
            return replace(self, page=1)
        if not self.clamp_page:
            return self
        last = max(1, math.ceil(total / self.per_page))
        return replace(self, page=min(self.page, last))

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page if self.per_page else 0


@dataclass
class LinkPage:
    links: List[Dict[str, Any]]
    total: int          # links matching the filter, across all pages
    query: LinkQuery    # with page clamped to a page that exists

    @property
    def pages(self) -> int:
        if not self.query.per_page:
            return 1
        return max(1, math.ceil(self.total / self.query.per_page))

    @property
    def first(self) -> int:
        """1-based position of the first link shown, 0 when there are none."""
        return self.query.offset + 1 if self.links else 0

    @property
    def last(self) -> int:
        return self.query.offset + len(self.links)


def link_sql(lq: LinkQuery, rank_col: str) -> Tuple[str, list, str]:
    """WHERE and ORDER BY clauses for the SQL backends (%s placeholders).

    Every identifier and keyword comes from a fixed list; user input only
    ever goes into the returned params."""
    where, params = ["user_id = %s"], []
    if lq.q:
        like = "%" + (lq.q.lower().replace("\\", "\\\\")
                      .replace("%", "\\%").replace("_", "\\_")) + "%"
        where.append("(LOWER(title) LIKE %s OR LOWER(url) LIKE %s)")
        params += [like, like]
    if lq.rank_op:
        sql_op = "=" if lq.rank_op == "==" else lq.rank_op
        where.append(f"{rank_col} {sql_op} %s")
        params.append(lq.rank_val)
    if lq.group == UNGROUPED:
        where.append("(group_id IS NULL OR group_id = '')")
    elif lq.group:
        where.append("group_id = %s")
        params.append(lq.group)
    sort_col = {"rank": rank_col, "title": "LOWER(title)", "url": "LOWER(url)"}[lq.sort]
    direction = "DESC" if lq.direction == "desc" else "ASC"
    # id breaks ties so rows never repeat or go missing between pages.
    order = f"{sort_col} {direction}, id ASC"
    return " AND ".join(where), params, order


def query_links_in_memory(links: List[Dict[str, Any]], lq: LinkQuery) -> LinkPage:
    if lq.q:
        q = lq.q.lower()
        links = [l for l in links if q in (l.get("title") or "").lower()
                                   or q in (l.get("url") or "").lower()]
    if lq.rank_op:
        cmp = RANK_OPS[lq.rank_op]
        links = [l for l in links if cmp(int(l.get("rank") or 0), lq.rank_val)]
    if lq.group == UNGROUPED:
        links = [l for l in links if not l.get("group_id")]
    elif lq.group:
        links = [l for l in links if l.get("group_id") == lq.group]
    key = {
        "rank":  lambda l: int(l.get("rank") or 0),
        "title": lambda l: (l.get("title") or "").lower(),
        "url":   lambda l: (l.get("url") or "").lower(),
    }[lq.sort]
    links = sorted(links, key=key, reverse=(lq.direction == "desc"))
    lq = lq.clamp(len(links))
    shown = links[lq.offset:lq.offset + lq.per_page] if lq.per_page else links
    return LinkPage(links=shown, total=len(links), query=lq)


class StoragePlugin(ABC):

    # ── Links ──────────────────────────────────────────────────────────────

    def query_links(self, user_id: str, lq: LinkQuery) -> LinkPage:
        """Return one page of a user's links after filtering and sorting.

        This default loads every link and works in memory, which is fine for
        the file backends (they read the whole file anyway). Database
        backends override it to filter, count and page in SQL."""
        return query_links_in_memory(self.get_all(user_id), lq)

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
