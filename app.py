import os
import sys
import secrets
import hashlib
import importlib
import logging
import bcrypt
from functools import wraps
from datetime import timedelta
from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, flash, session, g)
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "stelr-secret-change-me")
APP_VERSION = "5.0.3"
APP_NAME = "Stelr"

SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "xml").lower()
ADMIN_USERNAME  = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD")  # None if unset -- see _ensure_admin

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Your session has expired. Please log in again."
login_manager.login_message_category = "info"


@app.before_request
def enforce_session_timeout():
    session.permanent = True


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        plugin_map = {
            "xml":        ("plugins.xml_plugin",        "XmlPlugin"),
            "html":       ("plugins.html_plugin",       "HtmlPlugin"),
            "yaml":       ("plugins.yaml_plugin",       "YamlPlugin"),
            "mysql":      ("plugins.mysql_plugin",      "MysqlPlugin"),
            "postgresql": ("plugins.postgresql_plugin", "PostgresqlPlugin"),
        }
        if STORAGE_BACKEND not in plugin_map:
            raise ValueError(f"Unknown backend '{STORAGE_BACKEND}'.")
        mod_path, cls_name = plugin_map[STORAGE_BACKEND]
        logger.info(f"Loading backend: {STORAGE_BACKEND}")
        try:
            module = importlib.import_module(mod_path)
            _storage = getattr(module, cls_name)()
            _ensure_admin(_storage)
            logger.info(f"Backend '{STORAGE_BACKEND}' ready.")
        except Exception as e:
            logger.error(f"Backend init failed: {e}")
            raise
    return _storage


def _ensure_admin(storage):
    existing = storage.get_user_by_username(ADMIN_USERNAME)
    if not existing:
        password = ADMIN_PASSWORD
        if not password:
            # No fixed default on purpose -- a well-known admin/admin
            # credential is a real risk for a self-hosted, internet-facing
            # app. Generate one instead and only ever show it here, once.
            password = secrets.token_urlsafe(16)
            logger.warning("=" * 64)
            logger.warning(f"No ADMIN_PASSWORD set. Generated one for '{ADMIN_USERNAME}':")
            logger.warning(f"    {password}")
            logger.warning("This will not be shown again. If you lose it, the only")
            logger.warning("recovery today is wiping the data volume and starting over --")
            logger.warning("set ADMIN_PASSWORD yourself to avoid that.")
            logger.warning("=" * 64)
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        storage.create_user(ADMIN_USERNAME, pw_hash, is_admin=True, approved=True)
        logger.info(f"Admin account '{ADMIN_USERNAME}' created.")


def registration_enabled():
    return get_storage().get_setting("registration_enabled", "true") == "true"


# ── Flask-Login user class ─────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, data: dict):
        self.id       = data["id"]
        self.username = data["username"]
        self.is_admin = data.get("is_admin", False)


@login_manager.user_loader
def load_user(user_id):
    data = get_storage().get_user_by_id(user_id)
    return User(data) if data else None


# ── Auth routes ────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_data = get_storage().get_user_by_username(username)
        if user_data and bcrypt.checkpw(password.encode(),
                                         user_data["password_hash"].encode()):
            login_user(User(user_data))
            return redirect(request.args.get("next") or url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html", app_name=APP_NAME, version=APP_VERSION,
                           timeout=SESSION_TIMEOUT_MINUTES,
                           reg_enabled=registration_enabled())


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if not registration_enabled():
        flash("Registration is currently disabled. Please contact an administrator.", "info")
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")
        if not username or not password:
            flash("Username and password are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif get_storage().get_user_by_username(username):
            flash("That username is already taken.", "error")
        else:
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            get_storage().create_user(username, pw_hash, is_admin=False, approved=False)
            flash("Registration submitted! Your account is pending admin approval.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", app_name=APP_NAME, version=APP_VERSION)


# ── Main app routes ────────────────────────────────────────────────────────

RANK_OPS = {
    "<":  lambda rank, val: rank < val,
    "<=": lambda rank, val: rank <= val,
    "==": lambda rank, val: rank == val,
    ">=": lambda rank, val: rank >= val,
    ">":  lambda rank, val: rank > val,
}


def filter_links(links, query, rank_op, rank_val):
    if query:
        q = query.lower()
        links = [l for l in links if q in l.get("title", "").lower()
                                   or q in l.get("url", "").lower()]
    if rank_op in RANK_OPS and rank_val:
        try:
            rank_val_int = int(rank_val)
        except ValueError:
            return links
        cmp = RANK_OPS[rank_op]
        links = [l for l in links if cmp(l.get("rank", 0), rank_val_int)]
    return links


def filter_by_group(links, group_filter):
    if group_filter == "__ungrouped__":
        return [l for l in links if not l.get("group_id")]
    if group_filter:
        return [l for l in links if l.get("group_id") == group_filter]
    return links


SORT_FIELDS = {
    "rank":  lambda l: l.get("rank", 0),
    "title": lambda l: l.get("title", "").lower(),
    "url":   lambda l: l.get("url", "").lower(),
}


def sort_links(links, sort_field, direction):
    key_fn = SORT_FIELDS.get(sort_field, SORT_FIELDS["rank"])
    return sorted(links, key=key_fn, reverse=(direction == "desc"))


def resolve_group_id(storage, user_id, group_id):
    """Return group_id if it belongs to user_id, else ''."""
    if not group_id:
        return ""
    valid_ids = {g["id"] for g in storage.get_groups(user_id)}
    return group_id if group_id in valid_ids else ""


@app.route("/")
@login_required
def index():
    storage = get_storage()
    links  = storage.get_all(current_user.id)
    groups = storage.get_groups(current_user.id)
    group_map = {g["id"]: g["name"] for g in groups}
    api_tokens = storage.get_api_tokens(current_user.id)

    query        = request.args.get("q", "").strip()
    rank_op      = request.args.get("rank_op", "").strip()
    rank_val     = request.args.get("rank_val", "").strip()
    group_filter = request.args.get("group", "").strip()
    sort_field   = request.args.get("sort", "rank").strip()
    sort_dir     = request.args.get("dir", "asc").strip()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"
    if sort_field not in SORT_FIELDS:
        sort_field = "rank"

    links = filter_links(links, query, rank_op, rank_val)
    links = filter_by_group(links, group_filter)
    links = sort_links(links, sort_field, sort_dir)

    return render_template("index.html", links=links, groups=groups, group_map=group_map,
                           api_tokens=api_tokens,
                           backend=STORAGE_BACKEND, version=APP_VERSION, app_name=APP_NAME,
                           timeout=SESSION_TIMEOUT_MINUTES,
                           filter_q=query, filter_rank_op=rank_op, filter_rank_val=rank_val,
                           filter_group=group_filter, sort_field=sort_field, sort_dir=sort_dir)


@app.route("/add", methods=["POST"])
@login_required
def add():
    titles    = request.form.getlist("title")
    urls      = request.form.getlist("url")
    ranks     = request.form.getlist("rank")
    group_ids = request.form.getlist("group_id")

    storage = get_storage()
    added = 0
    for title, url, rank, group_id in zip(titles, urls, ranks, group_ids):
        title = title.strip()
        url = url.strip()
        if not title or not url:
            continue
        try:
            rank = int(rank)
        except ValueError:
            rank = 0
        group_id = resolve_group_id(storage, current_user.id, group_id.strip())
        storage.add({"user_id": current_user.id, "title": title,
                     "url": url, "rank": rank, "group_id": group_id})
        added += 1

    if added == 0:
        flash("Title and URL are required.", "error")
    elif added == 1:
        flash("Link added!", "success")
    else:
        flash(f"{added} links added!", "success")
    return redirect(url_for("index"))


@app.route("/delete/<link_id>", methods=["POST"])
@login_required
def delete(link_id):
    get_storage().delete(link_id, current_user.id)
    flash("Link deleted.", "info")
    return redirect(url_for("index"))


@app.route("/groups/create", methods=["POST"])
@login_required
def create_group():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Group name is required.", "error")
    else:
        get_storage().create_group(current_user.id, name)
        flash(f"Group '{name}' created.", "success")
    return redirect(url_for("index"))


@app.route("/groups/rename/<group_id>", methods=["POST"])
@login_required
def rename_group(group_id):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Group name is required.", "error")
    else:
        get_storage().rename_group(group_id, current_user.id, name)
        flash("Group renamed.", "success")
    return redirect(url_for("index"))


@app.route("/groups/delete/<group_id>", methods=["POST"])
@login_required
def delete_group(group_id):
    get_storage().delete_group(group_id, current_user.id)
    flash("Group deleted. Its links are now ungrouped.", "info")
    return redirect(url_for("index"))


@app.route("/change_password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password     = request.form.get("new_password", "")
    confirm          = request.form.get("confirm_password", "")
    user_data = get_storage().get_user_by_id(current_user.id)
    if not user_data or not bcrypt.checkpw(current_password.encode(),
                                            user_data["password_hash"].encode()):
        flash("Current password is incorrect.", "error")
    elif len(new_password) < 6:
        flash("New password must be at least 6 characters.", "error")
    elif new_password != confirm:
        flash("New passwords do not match.", "error")
    else:
        pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        get_storage().set_password(current_user.id, pw_hash)
        flash("Password changed successfully.", "success")
    return redirect(url_for("index"))


@app.route("/update/<link_id>", methods=["POST"])
@login_required
def update(link_id):
    title    = request.form.get("title", "").strip()
    url      = request.form.get("url", "").strip()
    rank     = request.form.get("rank", "0").strip()
    group_id = request.form.get("group_id", "").strip()
    try:
        rank = int(rank)
    except ValueError:
        rank = 0
    storage = get_storage()
    group_id = resolve_group_id(storage, current_user.id, group_id)
    storage.update(link_id, {"title": title, "url": url, "rank": rank, "group_id": group_id},
                    current_user.id)
    flash("Link updated.", "success")
    return redirect(url_for("index"))


# ── Admin routes ───────────────────────────────────────────────────────────

@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    storage = get_storage()
    all_links = storage.get_all_links_admin()
    # Build {user_id: [links]} map for the admin panel JS
    links_by_user = {}
    for link in all_links:
        uid = link.get("user_id", "")
        if uid not in links_by_user:
            links_by_user[uid] = []
        links_by_user[uid].append({
            "rank":  link.get("rank", 0),
            "title": link.get("title", ""),
            "url":   link.get("url", ""),
        })
    return render_template("admin.html",
                           users=storage.get_all_users(),
                           pending=storage.get_pending_users(),
                           links=all_links,
                           links_by_user=links_by_user,
                           backend=STORAGE_BACKEND,
                           version=APP_VERSION,
                           app_name=APP_NAME,
                           timeout=SESSION_TIMEOUT_MINUTES,
                           reg_enabled=registration_enabled())


@app.route("/admin/create_user", methods=["POST"])
@login_required
def admin_create_user():
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_admin = request.form.get("is_admin") == "1"
    if not username or not password:
        flash("Username and password are required.", "error")
    elif len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
    elif get_storage().get_user_by_username(username):
        flash(f"Username '{username}' is already taken.", "error")
    else:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        get_storage().create_user(username, pw_hash, is_admin=is_admin, approved=True)
        flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/approve_user/<user_id>", methods=["POST"])
@login_required
def admin_approve_user(user_id):
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    get_storage().approve_user(user_id)
    flash("User approved.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/reject_user/<user_id>", methods=["POST"])
@login_required
def admin_reject_user(user_id):
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    get_storage().reject_user(user_id)
    flash("Registration rejected and removed.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/delete_user/<user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin"))
    get_storage().delete_user(user_id)
    flash("User and their links deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/reset_password/<user_id>", methods=["POST"])
@login_required
def admin_reset_password(user_id):
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    password = request.form.get("password", "")
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin"))
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    get_storage().set_password(user_id, pw_hash)
    flash("Password reset.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/toggle_registration", methods=["POST"])
@login_required
def admin_toggle_registration():
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    current = registration_enabled()
    get_storage().set_setting("registration_enabled", "false" if current else "true")
    flash(f"Registration {'disabled' if current else 'enabled'}.", "success")
    return redirect(url_for("admin"))


# ── API auth helpers ───────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _request_data():
    """Return the request body as a dict, whether sent as JSON or form-encoded."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


def api_auth_required(f):
    """Accept either a Bearer API token or an existing session cookie."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            user_data = get_storage().get_user_by_token_hash(_hash_token(token))
            if not user_data:
                return jsonify({"error": "Invalid or revoked API token"}), 401
            g.api_user_id = user_data["id"]
            return f(*args, **kwargs)
        if current_user.is_authenticated:
            g.api_user_id = current_user.id
            return f(*args, **kwargs)
        return jsonify({"error": "Authentication required"}), 401
    return wrapper


def _get_link_for_user(storage, user_id, link_id):
    return next((l for l in storage.get_all(user_id) if l["id"] == link_id), None)


# ── API tokens ─────────────────────────────────────────────────────────────

@app.route("/api/tokens", methods=["POST"])
def api_create_token():
    """Bootstrap a token from username/password (for CLI login), or mint an
    additional token for an already session-authenticated browser user."""
    data = _request_data()
    name = (data.get("name") or "unnamed").strip() or "unnamed"

    if current_user.is_authenticated and not data.get("username"):
        user_id = current_user.id
    else:
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if not username or not password:
            return jsonify({"error": "username and password are required"}), 400
        storage = get_storage()
        user_data = storage.get_user_by_username(username)
        if not user_data or not bcrypt.checkpw(password.encode(),
                                                user_data["password_hash"].encode()):
            return jsonify({"error": "Invalid username or password"}), 401
        user_id = user_data["id"]

    raw_token = "stelr_" + secrets.token_urlsafe(32)
    token_id = get_storage().create_api_token(user_id, _hash_token(raw_token), name)
    return jsonify({"id": token_id, "name": name, "token": raw_token}), 201


@app.route("/api/tokens", methods=["GET"])
@api_auth_required
def api_list_tokens():
    return jsonify(get_storage().get_api_tokens(g.api_user_id))


@app.route("/api/tokens/<token_id>", methods=["DELETE"])
@api_auth_required
def api_revoke_token(token_id):
    get_storage().revoke_api_token(token_id, g.api_user_id)
    return jsonify({"status": "revoked"})


# ── API links ──────────────────────────────────────────────────────────────

@app.route("/api/links", methods=["GET"])
@api_auth_required
def api_links():
    links = get_storage().get_all(g.api_user_id)

    query        = request.args.get("q", "").strip()
    rank_op      = request.args.get("rank_op", "").strip()
    rank_val     = request.args.get("rank_val", "").strip()
    group_filter = request.args.get("group", "").strip()
    sort_field   = request.args.get("sort", "rank").strip()
    sort_dir     = request.args.get("dir", "asc").strip()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"
    if sort_field not in SORT_FIELDS:
        sort_field = "rank"

    links = filter_links(links, query, rank_op, rank_val)
    links = filter_by_group(links, group_filter)
    links = sort_links(links, sort_field, sort_dir)
    return jsonify(links)


@app.route("/api/links", methods=["POST"])
@api_auth_required
def api_create_link():
    data = _request_data()
    title = (data.get("title") or "").strip()
    url = (data.get("url") or "").strip()
    if not title or not url:
        return jsonify({"error": "title and url are required"}), 400
    try:
        rank = int(data.get("rank") or 0)
    except (TypeError, ValueError):
        rank = 0
    storage = get_storage()
    group_id = resolve_group_id(storage, g.api_user_id, str(data.get("group_id") or "").strip())
    link_id = storage.add({"user_id": g.api_user_id, "title": title, "url": url,
                           "rank": rank, "group_id": group_id})
    return jsonify(_get_link_for_user(storage, g.api_user_id, link_id)), 201


@app.route("/api/links/<link_id>", methods=["GET"])
@api_auth_required
def api_get_link(link_id):
    link = _get_link_for_user(get_storage(), g.api_user_id, link_id)
    if not link:
        return jsonify({"error": "Link not found"}), 404
    return jsonify(link)


@app.route("/api/links/<link_id>", methods=["PUT"])
@api_auth_required
def api_update_link(link_id):
    storage = get_storage()
    existing = _get_link_for_user(storage, g.api_user_id, link_id)
    if not existing:
        return jsonify({"error": "Link not found"}), 404
    data = _request_data()

    title = data.get("title")
    title = title.strip() if title is not None else existing["title"]
    url = data.get("url")
    url = url.strip() if url is not None else existing["url"]
    if not title or not url:
        return jsonify({"error": "title and url cannot be empty"}), 400

    rank = data.get("rank")
    if rank is not None:
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            rank = existing["rank"]
    else:
        rank = existing["rank"]

    group_id = data.get("group_id")
    group_id = (resolve_group_id(storage, g.api_user_id, str(group_id).strip())
               if group_id is not None else existing.get("group_id", ""))

    storage.update(link_id, {"title": title, "url": url, "rank": rank, "group_id": group_id},
                    g.api_user_id)
    return jsonify(_get_link_for_user(storage, g.api_user_id, link_id))


@app.route("/api/links/<link_id>", methods=["DELETE"])
@api_auth_required
def api_delete_link(link_id):
    storage = get_storage()
    if not _get_link_for_user(storage, g.api_user_id, link_id):
        return jsonify({"error": "Link not found"}), 404
    storage.delete(link_id, g.api_user_id)
    return jsonify({"status": "deleted"})


# ── API groups ─────────────────────────────────────────────────────────────

@app.route("/api/groups", methods=["GET"])
@api_auth_required
def api_groups():
    return jsonify(get_storage().get_groups(g.api_user_id))


@app.route("/api/groups", methods=["POST"])
@api_auth_required
def api_create_group():
    name = (_request_data().get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    group_id = get_storage().create_group(g.api_user_id, name)
    return jsonify({"id": group_id, "user_id": g.api_user_id, "name": name}), 201


@app.route("/api/groups/<group_id>", methods=["PUT"])
@api_auth_required
def api_rename_group(group_id):
    name = (_request_data().get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    get_storage().rename_group(group_id, g.api_user_id, name)
    return jsonify({"id": group_id, "user_id": g.api_user_id, "name": name})


@app.route("/api/groups/<group_id>", methods=["DELETE"])
@api_auth_required
def api_delete_group(group_id):
    get_storage().delete_group(group_id, g.api_user_id)
    return jsonify({"status": "deleted"})


# ── Health ─────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION, "backend": STORAGE_BACKEND})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
