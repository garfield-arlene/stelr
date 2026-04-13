import os
import importlib
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from plugins.base import StoragePlugin

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "stelr-secret-2025")
APP_VERSION = "1.0.0"
APP_NAME = "Stelr"

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "xml").lower()

def get_plugin() -> StoragePlugin:
    plugin_map = {
        "xml":        ("plugins.xml_plugin",        "XmlPlugin"),
        "html":       ("plugins.html_plugin",       "HtmlPlugin"),
        "yaml":       ("plugins.yaml_plugin",       "YamlPlugin"),
        "mysql":      ("plugins.mysql_plugin",      "MysqlPlugin"),
        "postgresql": ("plugins.postgresql_plugin", "PostgresqlPlugin"),
    }
    if STORAGE_BACKEND not in plugin_map:
        raise ValueError(f"Unknown storage backend: {STORAGE_BACKEND}")
    module_path, class_name = plugin_map[STORAGE_BACKEND]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()

storage = get_plugin()

@app.route("/")
def index():
    links = storage.get_all()
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
    storage.add({"title": title, "url": url, "rank": rank})
    flash(f"'{title}' added!", "success")
    return redirect(url_for("index"))

@app.route("/delete/<link_id>", methods=["POST"])
def delete(link_id):
    storage.delete(link_id)
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
    storage.update(link_id, {"title": title, "url": url, "rank": rank})
    flash("Link updated.", "success")
    return redirect(url_for("index"))

@app.route("/api/links", methods=["GET"])
def api_links():
    links = storage.get_all()
    links.sort(key=lambda x: x.get("rank", 0))
    return jsonify(links)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
