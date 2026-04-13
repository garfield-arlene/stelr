import os
import sys
import importlib
import logging
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash

# Ensure the app directory is always on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "stelr-secret-2025")
APP_VERSION = "1.0.0"
APP_NAME = "Stelr"

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "xml").lower()

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
            raise ValueError(f"Unknown storage backend: '{STORAGE_BACKEND}'. "
                             f"Valid options: {', '.join(plugin_map)}")
        module_path, class_name = plugin_map[STORAGE_BACKEND]
        logger.info(f"Loading storage backend: {STORAGE_BACKEND} ({module_path}.{class_name})")
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            _storage = cls()
            logger.info(f"Storage backend '{STORAGE_BACKEND}' initialised successfully.")
        except Exception as e:
            logger.error(f"Failed to initialise storage backend '{STORAGE_BACKEND}': {e}")
            raise
    return _storage

@app.route("/")
def index():
    links = get_storage().get_all()
    links.sort(key=lambda x: x.get("rank", 0))
    return render_template("index.html", links=links, backend=STORAGE_BACKEND,
                           version=APP_VERSION, app_name=APP_NAME)

@app.route("/add", methods=["POST"])
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
    get_storage().add({"title": title, "url": url, "rank": rank})
    flash(f"'{title}' added!", "success")
    return redirect(url_for("index"))

@app.route("/delete/<link_id>", methods=["POST"])
def delete(link_id):
    get_storage().delete(link_id)
    flash("Link deleted.", "info")
    return redirect(url_for("index"))

@app.route("/update/<link_id>", methods=["POST"])
def update(link_id):
    title = request.form.get("title", "").strip()
    url   = request.form.get("url", "").strip()
    rank  = request.form.get("rank", "0").strip()
    try:
        rank = int(rank)
    except ValueError:
        rank = 0
    get_storage().update(link_id, {"title": title, "url": url, "rank": rank})
    flash("Link updated.", "success")
    return redirect(url_for("index"))

@app.route("/api/links", methods=["GET"])
def api_links():
    links = get_storage().get_all()
    links.sort(key=lambda x: x.get("rank", 0))
    return jsonify(links)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION, "backend": STORAGE_BACKEND})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
