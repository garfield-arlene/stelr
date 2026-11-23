"""Per-user dashboard wallpapers.

Images come from a provider (Pixabay today). The provider's API key is
set once per server by the admin, either on the Admin page (stored
encrypted, see secret_box.py) or with the PIXABAY_API_KEY environment
variable, which takes precedence. The key is only ever sent to Pixabay
over verified HTTPS and is never sent to browsers or written to logs.

Pixabay's API terms
say search results must be cached for 24 hours and images must not be
permanently hotlinked, so search results and chosen images are both
cached on disk here, and the browser only ever loads images from Stelr.
"""
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import secret_box

logger = logging.getLogger(__name__)

PIXABAY_API_URL = "https://pixabay.com/api/"
PIXABAY_KEY_SETTING = "pixabay_api_key"
# Pixabay keys look like "12345678-0123456789abcdef0123456789a".
PIXABAY_KEY_RE = re.compile(r"^[A-Za-z0-9-]{10,100}$")

SEARCH_CACHE_SECONDS = 24 * 60 * 60
IMAGE_CACHE_SECONDS = 14 * 24 * 60 * 60
MAX_IMAGE_BYTES = 10 * 1024 * 1024
HTTP_TIMEOUT = 8

ROTATIONS = ("daily", "login", "manual")
MODES = ("random", "keywords")
RANDOM_CATEGORIES = ("backgrounds", "nature", "places")

DEFAULTS = {
    "enabled": False,
    "provider": "pixabay",
    "mode": "random",
    "keywords": "",
    "rotation": "daily",
    "dim": 80,      # overlay opacity in percent
    "blur": True,
    "current": None,
}


class WallpaperError(Exception):
    pass


# ── Providers ──────────────────────────────────────────────────────────────

PROVIDERS = {
    "pixabay": {
        "name": "Pixabay",
        "url": "https://pixabay.com/",
    },
}


# ── API key ────────────────────────────────────────────────────────────────

def _env_key() -> str:
    return os.environ.get("PIXABAY_API_KEY", "").strip()


def get_api_key(storage) -> str:
    """The Pixabay key to use, or "" if none is usable. Never log this."""
    if _env_key():
        return _env_key()
    stored = storage.get_setting(PIXABAY_KEY_SETTING, "")
    if not stored:
        return ""
    try:
        return secret_box.decrypt(stored)
    except secret_box.SecretBoxError:
        return ""


def key_status(storage) -> dict:
    """What the admin page shows: where the key comes from, never the key."""
    if _env_key():
        return {"source": "env", "hint": _hint(_env_key()), "error": None}
    stored = storage.get_setting(PIXABAY_KEY_SETTING, "")
    if not stored:
        return {"source": None, "hint": "", "error": None}
    try:
        return {"source": "db", "hint": _hint(secret_box.decrypt(stored)), "error": None}
    except secret_box.SecretBoxError as e:
        return {"source": "db", "hint": "", "error": str(e)}


def _hint(key: str) -> str:
    return "…" + key[-4:] if len(key) > 8 else "…"


def save_api_key(storage, key: str, user_agent: str):
    """Check the key against Pixabay, then store it encrypted."""
    key = (key or "").strip()
    if not PIXABAY_KEY_RE.match(key):
        raise WallpaperError("That doesn't look like a Pixabay API key.")
    encrypted = secret_box.encrypt(key)  # fails early on a weak SECRET_KEY
    _pixabay_request({"q": "", "per_page": 3}, key, user_agent)
    storage.set_setting(PIXABAY_KEY_SETTING, encrypted)


def delete_api_key(storage):
    storage.set_setting(PIXABAY_KEY_SETTING, "")


def provider_configured(storage, provider: str = "pixabay") -> bool:
    if provider == "pixabay":
        return bool(get_api_key(storage))
    return False


def providers_for_template(storage):
    return [{"id": pid, "name": p["name"], "url": p["url"],
             "configured": provider_configured(storage, pid)}
            for pid, p in PROVIDERS.items()]


# ── Cache dir ──────────────────────────────────────────────────────────────

_cache_dir = None


def cache_dir() -> str:
    global _cache_dir
    if _cache_dir:
        return _cache_dir
    candidates = [os.environ.get("WALLPAPER_CACHE_DIR", "").strip(),
                  "/data/wallpaper-cache",
                  os.path.join(tempfile.gettempdir(), "stelr-wallpaper-cache")]
    for path in candidates:
        if not path:
            continue
        try:
            os.makedirs(path, exist_ok=True)
            if os.access(path, os.W_OK):
                _cache_dir = path
                return path
        except OSError:
            continue
    raise WallpaperError("No writable wallpaper cache directory.")


def _atomic_write(path: str, data: bytes):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _prune_cache():
    """Drop cached images and searches nobody has used in a while."""
    cutoff = time.time() - IMAGE_CACHE_SECONDS
    try:
        for name in os.listdir(cache_dir()):
            path = os.path.join(cache_dir(), name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.unlink(path)
            except OSError:
                pass
    except (OSError, WallpaperError):
        pass


# ── User settings (stored via the backend's key/value settings) ────────────

def _settings_key(user_id: str) -> str:
    # Kept to [A-Za-z0-9_-] so it's also a valid XML element name for the
    # XML backend, which stores each setting as its own element.
    return "wallpaper_" + re.sub(r"[^A-Za-z0-9_-]", "", str(user_id))


def load_settings(storage, user_id) -> dict:
    settings = dict(DEFAULTS)
    raw = storage.get_setting(_settings_key(user_id), "")
    if raw:
        try:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                settings.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except ValueError:
            pass
    return settings


def save_settings(storage, user_id, settings: dict):
    clean = {k: settings.get(k, v) for k, v in DEFAULTS.items()}
    storage.set_setting(_settings_key(user_id), json.dumps(clean))


def normalize_form(form, existing: dict) -> dict:
    """Validate submitted settings, keeping the current image."""
    settings = dict(existing)
    settings["enabled"] = form.get("enabled") in ("1", "on", "true", True)
    provider = form.get("provider", "pixabay")
    settings["provider"] = provider if provider in PROVIDERS else "pixabay"
    mode = form.get("mode", "random")
    settings["mode"] = mode if mode in MODES else "random"
    settings["keywords"] = ", ".join(parse_keywords(form.get("keywords", "")))
    rotation = form.get("rotation", "daily")
    settings["rotation"] = rotation if rotation in ROTATIONS else "daily"
    try:
        settings["dim"] = max(40, min(95, int(form.get("dim", 80))))
    except (TypeError, ValueError):
        settings["dim"] = 80
    settings["blur"] = form.get("blur") in ("1", "on", "true", True)
    return settings


def parse_keywords(text: str) -> list:
    words = [w.strip() for w in re.split(r"[,\n]", text or "")]
    # Pixabay caps q at 100 chars; keep each keyword well under that.
    return [w[:60] for w in words if w][:20]


# ── Pixabay ────────────────────────────────────────────────────────────────

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects, so a request can never be bounced to plain HTTP
    or to another host (which would carry the API key in its URL)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused", headers, fp)


# urllib verifies TLS certificates and hostnames by default; this opener
# keeps that and only removes redirect-following.
_opener = urllib.request.build_opener(_NoRedirect)


def _http_get(url: str, user_agent: str, max_bytes: int) -> bytes:
    if not url.startswith("https://"):
        raise WallpaperError("Refusing a non-HTTPS request.")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with _opener.open(req, timeout=HTTP_TIMEOUT) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise WallpaperError("Response too large.")
    return data


def _pixabay_request(params: dict, api_key: str, user_agent: str) -> bytes:
    """Call the Pixabay API. Pixabay only accepts the key as a query
    parameter, so the URL is secret: it's encrypted in transit by TLS, and
    nothing derived from it (including exception text) is logged or
    returned to the caller."""
    url = PIXABAY_API_URL + "?" + urllib.parse.urlencode(dict(params, key=api_key))
    try:
        return _http_get(url, user_agent, 2 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise WallpaperError("Pixabay rate limit reached; try again in a minute.") from None
        if e.code in (400, 401, 403):
            raise WallpaperError("Pixabay rejected the API key.") from None
        raise WallpaperError(f"Pixabay returned HTTP {e.code}.") from None
    except (urllib.error.URLError, OSError):
        raise WallpaperError("Could not reach Pixabay.") from None


def _pixabay_search(query: str, category: str, editors_choice: bool,
                    api_key: str, user_agent: str) -> list:
    params = {
        "q": query[:100],
        "image_type": "photo",
        "orientation": "horizontal",
        "min_width": 1920,
        "min_height": 1080,
        "safesearch": "true",
        "order": "popular",
        "per_page": 100,
    }
    if category:
        params["category"] = category
    if editors_choice:
        params["editors_choice"] = "true"

    cache_id = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:24]
    cache_path = os.path.join(cache_dir(), f"search-{cache_id}.json")
    try:
        if time.time() - os.path.getmtime(cache_path) < SEARCH_CACHE_SECONDS:
            with open(cache_path) as f:
                return json.load(f)
    except (OSError, ValueError):
        pass

    body = _pixabay_request(params, api_key, user_agent)
    try:
        hits = json.loads(body).get("hits", [])
    except ValueError:
        raise WallpaperError("Pixabay returned an unreadable response.")
    hits = [{"id": int(h["id"]),
             "image": h.get("largeImageURL", ""),
             "page": h.get("pageURL", ""),
             "user": h.get("user", ""),
             "tags": h.get("tags", "")}
            for h in hits if h.get("id") and h.get("largeImageURL")]
    _atomic_write(cache_path, json.dumps(hits).encode())
    return hits


def _is_pixabay_url(url: str) -> bool:
    parts = urllib.parse.urlparse(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "pixabay.com" or host.endswith(".pixabay.com"))


def _download_image(hit: dict, user_agent: str):
    path = image_path(hit["id"])
    if os.path.exists(path):
        os.utime(path)
        return
    if not _is_pixabay_url(hit["image"]):
        raise WallpaperError("Unexpected image host.")
    try:
        data = _http_get(hit["image"], user_agent, MAX_IMAGE_BYTES)
    except (urllib.error.URLError, OSError):
        raise WallpaperError("Could not download image.") from None
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
        raise WallpaperError("Downloaded file is not an image.")
    _atomic_write(path, data)


def image_path(image_id) -> str:
    return os.path.join(cache_dir(), f"pixabay-{int(image_id)}.img")


def image_mimetype(path: str) -> str:
    with open(path, "rb") as f:
        head = f.read(8)
    return "image/png" if head.startswith(b"\x89PNG") else "image/jpeg"


def _pick_hit(settings: dict, api_key: str, user_agent: str, exclude_id=None) -> dict:
    searches = []
    keywords = parse_keywords(settings.get("keywords", ""))
    if settings.get("mode") == "keywords" and keywords:
        # Pixabay ANDs every word in q, so a long keyword list returns
        # few or no results. Use one randomly chosen keyword per pick.
        random.shuffle(keywords)
        searches += [(kw, "", False) for kw in keywords[:3]]
    categories = list(RANDOM_CATEGORIES)
    random.shuffle(categories)
    searches.append(("", categories[0], True))

    for query, category, editors in searches:
        hits = _pixabay_search(query, category, editors, api_key, user_agent)
        choices = [h for h in hits if h["id"] != exclude_id] or hits
        if choices:
            return random.choice(choices)
    raise WallpaperError("No images found.")


# ── Public entry points ────────────────────────────────────────────────────

def _needs_new_image(settings: dict, session_flag: bool) -> bool:
    current = settings.get("current")
    if not current or not os.path.exists(image_path(current["id"])):
        return True
    rotation = settings.get("rotation")
    if rotation == "daily":
        return current.get("date") != date.today().isoformat()
    if rotation == "login":
        return not session_flag
    return False


def current_image(settings: dict):
    """The user's current image if it is still cached, without any network."""
    current = settings.get("current")
    if not settings.get("enabled") or not current:
        return None
    try:
        if os.path.exists(image_path(current["id"])):
            return current
    except (WallpaperError, KeyError, TypeError, ValueError):
        pass
    return None


def resolve(storage, user_id, user_agent: str, session_flag: bool,
            force_new: bool = False):
    """Return the image to show, picking a new one when rotation is due."""
    settings = load_settings(storage, user_id)
    if not settings["enabled"]:
        return None
    if not force_new and not _needs_new_image(settings, session_flag):
        return settings["current"]
    api_key = get_api_key(storage)
    if not api_key:
        raise WallpaperError("No API key is configured for this wallpaper source.")

    old = settings.get("current") or {}
    hit = _pick_hit(settings, api_key, user_agent, exclude_id=old.get("id"))
    _download_image(hit, user_agent)
    settings["current"] = {
        "id": hit["id"],
        "page": hit["page"] if _is_pixabay_url(hit["page"]) else "https://pixabay.com/",
        "user": hit["user"],
        "tags": hit["tags"],
        "date": date.today().isoformat(),
    }
    save_settings(storage, user_id, settings)
    _prune_cache()
    return settings["current"]
