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
APP_VERSION = "2.0.0"
APP_NAME = "Stelr"

# Session timeout — default 30 minutes, override with SESSION_TIMEOUT_MINUTES env var
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
    """Make every session permanent so PERMANENT_SESSION_LIFETIME applies.
    When the cookie expires Flask-Login automatically redirects to login."""
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
            raise ValueError(f"Unknown backend '{STORAGE_BACKEND}'. "
                             f"Valid: {', '.join(plugin_map)}")
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
    """Create the admin account on first run if it doesn't exist."""
    existing = storage.get_user_by_username(ADMIN_USERNAME)
    if not existing:
        pw_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        storage.create_user(ADMIN_USERNAME, pw_hash, is_admin=True)
        logger.info(f"Admin account '{ADMIN_USERNAME}' created.")


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
                           timeout=SESSION_TIMEOUT_MINUTES)


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
            get_storage().create_user(username, pw_hash, is_admin=False)
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", app_name=APP_NAME, version=APP_VERSION)


# ── Main app routes ────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    links = get_storage().get_all(current_user.id)
    links.sort(key=lambda x: x.get("rank", 0))
    return render_template("index.html", links=links, backend=STORAGE_BACKEND,
                           version=APP_VERSION, app_name=APP_NAME,
                           timeout=SESSION_TIMEOUT_MINUTES)


@app.route("/add", methods=["POST"])
@login_required
def add():
    title = request.form.get("title", "").strip()
    url   = request.form.get("url", "").strip()
    rank  = request.form.get("rank", "0").strip()
    if not title or not url:
        flash("Title and URL are required.", "error")
        return redirect(url_for("index"))
    try:
        rank = int(rank)
    except ValueError:
        rank = 0
    get_storage().add({"user_id": current_user.id, "title": title,
                        "url": url, "rank": rank})
    flash(f"'{title}' added!", "success")
    return redirect(url_for("index"))


@app.route("/delete/<link_id>", methods=["POST"])
@login_required
def delete(link_id):
    get_storage().delete(link_id, current_user.id)
    flash("Link deleted.", "info")
    return redirect(url_for("index"))


@app.route("/update/<link_id>", methods=["POST"])
@login_required
def update(link_id):
    title = request.form.get("title", "").strip()
    url   = request.form.get("url", "").strip()
    rank  = request.form.get("rank", "0").strip()
    try:
        rank = int(rank)
    except ValueError:
        rank = 0
    get_storage().update(link_id, {"title": title, "url": url, "rank": rank},
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
    users = get_storage().get_all_users()
    links = get_storage().get_all_links_admin()
    return render_template("admin.html", users=users, links=links,
                           backend=STORAGE_BACKEND, version=APP_VERSION,
                           app_name=APP_NAME, timeout=SESSION_TIMEOUT_MINUTES)


@app.route("/admin/delete_user/<user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    if user_id == current_user.id:
        flash("You cannot delete your own admin account.", "error")
        return redirect(url_for("admin"))
    get_storage().delete_user(user_id)
    flash("User and their links deleted.", "info")
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
