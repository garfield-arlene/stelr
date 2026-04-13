# 🔗 Stelr

**v1.0.0**

A containerized Python web app for saving and ranking URLs, with a pluggable storage backend.

## Changelog

### v1.0.0 — Initial Release
- Add, edit, and delete bookmarked URLs with title, URL, and numeric rank
- Links sorted by rank ascending
- REST API endpoint: `GET /api/links`
- Pluggable storage backends: XML, YAML, HTML, MySQL, PostgreSQL
- Docker + Docker Compose support with backend profiles
- Dark industrial UI

---

## Storage Backends

| Backend    | `STORAGE_BACKEND` value | Notes                          |
|------------|------------------------|--------------------------------|
| XML        | `xml`                  | Default, file-based            |
| YAML       | `yaml`                 | Human-readable, file-based     |
| HTML       | `html`                 | Structured HTML data file      |
| MySQL      | `mysql`                | Requires MySQL 8+              |
| PostgreSQL | `postgresql`           | Requires PostgreSQL 15+        |

---

## Quick Start

### XML (default — no database needed)
```bash
docker compose up
```
Open http://localhost:5000

### YAML
```bash
docker compose --profile yaml up
```

### HTML
```bash
docker compose --profile html up
```

### MySQL
```bash
docker compose --profile mysql up
```

### PostgreSQL
```bash
docker compose --profile postgresql up
```

---

## Environment Variables

| Variable           | Default           | Description                  |
|--------------------|-------------------|------------------------------|
| `STORAGE_BACKEND`  | `xml`             | Backend plugin to use        |
| `XML_FILE`         | `/data/links.xml` | Path for XML file            |
| `YAML_FILE`        | `/data/links.yaml`| Path for YAML file           |
| `HTML_FILE`        | `/data/links.html`| Path for HTML file           |
| `MYSQL_HOST`       | `mysql`           | MySQL host                   |
| `MYSQL_PORT`       | `3306`            | MySQL port                   |
| `MYSQL_USER`       | `stelr`           | MySQL user                   |
| `MYSQL_PASSWORD`   | `stelr`           | MySQL password               |
| `MYSQL_DATABASE`   | `stelr`           | MySQL database               |
| `POSTGRES_HOST`    | `postgres`        | PostgreSQL host              |
| `POSTGRES_PORT`    | `5432`            | PostgreSQL port              |
| `POSTGRES_USER`    | `stelr`           | PostgreSQL user              |
| `POSTGRES_PASSWORD`| `stelr`           | PostgreSQL password          |
| `POSTGRES_DB`      | `stelr`           | PostgreSQL database          |
| `SECRET_KEY`       | *(random)*        | Flask session secret key     |

---

## Writing a Custom Plugin

1. Create `plugins/myplugin.py` implementing the `StoragePlugin` ABC:

```python
from plugins.base import StoragePlugin

class MypluginPlugin(StoragePlugin):
    def get_all(self): ...
    def add(self, link): ...
    def delete(self, link_id): ...
    def update(self, link_id, link): ...
```

2. Register it in `app.py`'s `plugin_map` dict.
3. Set `STORAGE_BACKEND=myplugin`.

---

## REST API

```
GET  /api/links   → JSON array of all links, sorted by rank
```

Example response:
```json
[
  {"id": "uuid", "title": "Example", "url": "https://example.com", "rank": 1}
]
```

---

## Project Structure

```
stelr/
├── VERSION                       # Current version string
├── app.py                        # Flask app + routing
├── plugins/
│   ├── base.py                   # Abstract StoragePlugin
│   ├── xml_plugin.py
│   ├── yaml_plugin.py
│   ├── html_plugin.py
│   ├── mysql_plugin.py
│   └── postgresql_plugin.py
├── templates/
│   └── index.html                # Jinja2 template
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```
