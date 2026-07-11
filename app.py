import os
import sys
import importlib
import logging
import bcrypt
from datetime import timedelta
from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, flash, session)
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "stelr-secret-change-me")
APP_VERSION = "3.5.2"
APP_NAME = "Stelr"

SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "xml").lower()
ADMIN_USERNAME  = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "admin")

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
        pw_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
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
                           backend=STORAGE_BACKEND, version=APP_VERSION, app_name=APP_NAME,
                           timeout=SESSION_TIMEOUT_MINUTES,
                           filter_q=query, filter_rank_op=rank_op, filter_rank_val=rank_val,
                           filter_group=group_filter, sort_field=sort_field, sort_dir=sort_dir)


@app.route("/add", methods=["POST"])
@login_required
def add():
    title    = request.form.get("title", "").strip()
    url      = request.form.get("url", "").strip()
    rank     = request.form.get("rank", "0").strip()
    group_id = request.form.get("group_id", "").strip()
    if not title or not url:
        flash("Title and URL are required.", "error")
        return redirect(url_for("index"))
    try:
        rank = int(rank)
    except ValueError:
        rank = 0
    storage = get_storage()
    group_id = resolve_group_id(storage, current_user.id, group_id)
    storage.add({"user_id": current_user.id, "title": title,
                 "url": url, "rank": rank, "group_id": group_id})
    flash(f"'{title}' added!", "success")
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


# ── API & health ───────────────────────────────────────────────────────────

@app.route("/api/links")
@login_required
def api_links():
    links = get_storage().get_all(current_user.id)
    links.sort(key=lambda x: x.get("rank", 0))
    return jsonify(links)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION, "backend": STORAGE_BACKEND})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
