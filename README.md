# 🔗 Stelr

**v2.0.0**

Stelr is a web app for saving, organising, and ranking URLs. Add any link with a
title and a numeric rank — Stelr keeps them sorted and accessible from any browser.

---

## Features

- Save URLs with a title and rank
- Edit or delete any saved link
- Links are always displayed sorted by rank (lowest first)
- REST API for programmatic access
- Choice of storage backend — from simple files to full databases
- Data is persisted across restarts via Docker volumes

---

## Using the App

Open **http://localhost:5000** in your browser.

Dashboard
![Stelr Dashboard](screenshots/Stelr_Interface_Dashboard_2026-04-13.png)

### Adding a link
Fill in the **Title**, **URL**, and **Rank** fields at the top of the page and
click **Add**. Rank is a number — lower numbers appear first. You can use any
numbering scheme you like (1, 2, 3 or 10, 20, 30, etc.).

### Editing a link
Click the **Edit** button on any row to expand an inline edit form. Change the
fields you want and click **Save**.

![Editing a link](screenshots/Stelr_Edit_2026-04-13.png)

### Deleting a link
Click the **Delete** button on any row. You will be asked to confirm before the
link is removed.

### REST API
Two read-only endpoints are available:

| Endpoint      | Description                                    |
|---------------|------------------------------------------------|
| `/api/links`  | Returns all links as JSON, sorted by rank      |
| `/health`     | Returns app status, version, and active backend |

---

## Storage Backends

Stelr supports five storage backends, selected at startup via the
`STORAGE_BACKEND` environment variable. On first run, each backend will
automatically create any required directory, file, or database — no manual
setup is needed.

### XML (default)
Links are stored in a plain XML file. Good for simple setups with no external
dependencies.

```
STORAGE_BACKEND=xml
```

Data file location is controlled by `XML_FILE` (default: `/data/links.xml`).

---

### YAML
Links are stored in a YAML file — human-readable and easy to edit by hand.

```
STORAGE_BACKEND=yaml
```

Data file location is controlled by `YAML_FILE` (default: `/data/links.yaml`).

---

### HTML
Links are stored in a structured HTML file as a `<ul>` list with data
attributes. The file is valid HTML and can be opened directly in a browser.

```
STORAGE_BACKEND=html
```

Data file location is controlled by `HTML_FILE` (default: `/data/links.html`).

---

### MySQL
Links are stored in a MySQL database. Stelr will create the database and table
automatically on first run.

```
STORAGE_BACKEND=mysql
```

| Variable         | Default | Description       |
|------------------|---------|-------------------|
| `MYSQL_HOST`     | `mysql` | Hostname          |
| `MYSQL_PORT`     | `3306`  | Port              |
| `MYSQL_USER`     | `stelr` | Username          |
| `MYSQL_PASSWORD` | `stelr` | Password          |
| `MYSQL_DATABASE` | `stelr` | Database name     |

---

### PostgreSQL
Links are stored in a PostgreSQL database. Stelr will create the database and
table automatically on first run.

```
STORAGE_BACKEND=postgresql
```

| Variable            | Default    | Description   |
|---------------------|------------|---------------|
| `POSTGRES_HOST`     | `postgres` | Hostname      |
| `POSTGRES_PORT`     | `5432`     | Port          |
| `POSTGRES_USER`     | `stelr`    | Username      |
| `POSTGRES_PASSWORD` | `stelr`    | Password      |
| `POSTGRES_DB`       | `stelr`    | Database name |

---

## Starting Stelr

Use the `--profile` flag to select a backend. The app will always be available
at **http://localhost:5000**.

```bash
# XML (default)
podman compose up

# YAML
podman compose --profile yaml up

# HTML
podman compose --profile html up

# MySQL
podman compose --profile mysql up

# PostgreSQL
podman compose --profile postgresql up
```

To run in the background, add `-d`:

```bash
podman compose --profile yaml up -d
```

To stop:

```bash
podman compose --profile yaml stop
```
