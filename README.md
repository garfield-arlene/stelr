# 🔗 Stelr

**v4.1.0**

Stelr is a web app for saving, organising, and ranking URLs. Add any link with a
title and a numeric rank — Stelr keeps them sorted and accessible from any browser.
User accounts are required to access the app, with admin-controlled registration
and approval.

---

## New features and bug fixes

- Fixed slow add/delete on the MySQL and PostgreSQL backends by pooling database connections instead of opening a new one for every query

## Features

- Save URLs with a title and rank
- Edit or delete any saved link
- Links are always displayed sorted by rank (lowest first)
- User accounts with login, session timeout, and logout
- Admin-controlled user registration and approval queue
- REST API for programmatic access
- Choice of storage backend — from simple files to full databases
- Data is persisted across restarts via Docker volumes
- Admin can change user passwords
- User can change their own password
- Filter entries by keyword (substring) in title or URL
- Filter entries by rank using a numerical comparison (<, <=, ==, >=, >)
- Group links into folders, and sort entries by clicking a column header

## To do

- Update UI to hide URL on mobile devices
- Add ability to "click to add another entry" for the same "save call"

---

## Getting Started

Open **http://localhost:8082** in your browser. You will be presented with the
login page. On first run, an admin account is created automatically using the
credentials set in the compose file (default: `admin` / `admin`).

---

## User Accounts

### Logging In
Enter your username and password on the login page. Sessions expire after a
configurable timeout (default 30 minutes) and you will be redirected to the
login page automatically.

### Registering
If registration is enabled by an admin, a **Register** link appears on the login
page. Fill in a username and password (minimum 6 characters) and submit. Your
account will be placed in a pending queue and cannot be used until an admin
approves it. If registration is disabled, the link is hidden and a message
instructs you to contact an administrator.

### Changing Your Password
Click the **Change Password** button in the header. Enter your current
password plus a new password (minimum 6 characters, entered twice to catch
typos). Your current password must be correct for the change to take effect.

### Logging Out
Click the **Logout** button in the top-right corner of any page.

---

## Using the App

Dashboard
![Stelr Dashboard](screenshots/Stelr_Interface_Dashboard_2026-04-13.png)

### Adding a link
Fill in the **Title**, **URL**, and **Rank** fields at the top of the page and
click **Add**. Rank is a number — lower numbers appear first. You can use any
numbering scheme you like (1, 2, 3 or 10, 20, 30, etc.).

Dashboard
![Stelr Dashboard](screenshots/Stelr_Interface_Dashboard_2026-04-13.png)

### Editing a link
Click the **Edit** button on any row to expand an inline edit form. Change the
fields you want and click **Save**.

![Editing a link](screenshots/Stelr_Edit_2026-04-13.png)

### Deleting a link
Click the **Delete** button on any row. You will be asked to confirm before the
link is removed.

### Filtering links
Use the **Filter Links** panel above the table to narrow down what's shown.
Enter a keyword to match against the title or URL (case-insensitive substring
match), and/or pick a rank comparison (`<`, `<=`, `==`, `>=`, `>`) with a value
to only show links whose rank satisfies it. A **Group** dropdown in the same
panel narrows the list to a single group or to ungrouped links. Filters can
be combined. Click **Clear** to reset.

### Sorting links
Click any of the **Rank**, **Title**, or **URL** column headers to sort the
table by that column. Clicking the same header again reverses the direction;
an arrow next to the header shows the current sort field and direction.

### Organizing links into groups
Use the **Manage Groups** panel to create, rename, or delete groups (folders)
for your links. When adding or editing a link, pick a group from the
**Group** dropdown, or leave it as "No Group". Deleting a group does not
delete its links — they simply become ungrouped.

---

## Admin Panel

The admin panel is accessible via the **Admin** button in the header, visible
only to admin accounts. It is available at **/admin**.

### Registration Toggle
Enable or disable the public registration page with a single button. When
disabled, the register link is hidden from the login page and new users can
only be created directly by an admin.

### Pending Approvals
When registration is enabled, new sign-ups appear here awaiting approval. Each
entry can be **Approved** (activating the account) or **Rejected** (deleting
the registration). A warning badge in the header shows the number of pending
requests.

### Create User
Admins can create accounts directly, bypassing the registration queue. A
username, password, and optional admin flag can be set. Accounts created this
way are active immediately.

### Active Users
Lists all approved accounts. Each row has a **Reset PW** button that opens a
dialog to set a new password for that user (minimum 6 characters, entered
twice to catch typos) — no knowledge of their current password is required.
Non-admin users can be deleted, which also removes all of their saved links.
Admin accounts cannot be deleted.

### All Links
A read-only view of every link saved by every user, showing the owning username,
title, URL, and rank.

---

## REST API

Stelr exposes a small JSON API for reading your own links programmatically.
There's no separate API token — authentication reuses the same session
cookie as the web UI, so a client needs to log in first and carry that
cookie on subsequent requests.

| Endpoint      | Method | Auth required | Description                                      |
|---------------|--------|----------------|---------------------------------------------------|
| `/login`      | POST   | No             | Authenticate; sets the session cookie             |
| `/api/links`  | GET    | Yes            | Returns your links as JSON, sorted by rank        |
| `/health`     | GET    | No             | Returns app status, version, and active backend   |

### Authenticating

Log in with a cookie jar so the session persists across requests:

```bash
curl -c cookies.txt -X POST http://localhost:8082/login \
  -d "username=myuser" -d "password=mypassword"
```

### Fetching your links

```bash
curl -b cookies.txt http://localhost:8082/api/links
```

Example response:

```json
[
  {
    "id": "b6b9c2b0-3f1a-4e2c-9a1d-8f3e2c1d0a9b",
    "user_id": "1a2b3c4d-5e6f-4a1b-9c2d-3e4f5a6b7c8d",
    "title": "GitHub",
    "url": "https://github.com",
    "rank": 1,
    "group_id": ""
  }
]
```

`group_id` is an empty string when a link isn't assigned to a group.

### Health check

No authentication required — useful for uptime checks and container
healthchecks.

```bash
curl http://localhost:8082/health
```

```json
{"status": "ok", "version": "<version>", "backend": "xml"}
```

---

## Storage Backends

Stelr supports five storage backends, selected at startup via the
`STORAGE_BACKEND` environment variable. On first run, each backend will
automatically create any required directory, file, or database — no manual
setup is needed.

### XML (default)
Links and users are stored in a plain XML file.

```
STORAGE_BACKEND=xml
```

Data file location is controlled by `XML_FILE` (default: `/data/links.xml`).

---

### YAML
Links and users are stored in a YAML file — human-readable and easy to inspect.

```
STORAGE_BACKEND=yaml
```

Data file location is controlled by `YAML_FILE` (default: `/data/links.yaml`).

---

### HTML
Links and users are stored in a structured HTML file. User data is embedded as
JSON in a `<script>` tag; links are stored as a `<ul>` list.

```
STORAGE_BACKEND=html
```

Data file location is controlled by `HTML_FILE` (default: `/data/links.html`).

---

### MySQL
Links and users are stored in a MySQL database. Stelr will create the database
and tables automatically on first run.

```
STORAGE_BACKEND=mysql
```

| Variable         | Default | Description   |
|------------------|---------|---------------|
| `MYSQL_HOST`     | `mysql` | Hostname      |
| `MYSQL_PORT`     | `3306`  | Port          |
| `MYSQL_USER`     | `stelr` | Username      |
| `MYSQL_PASSWORD` | `stelr` | Password      |
| `MYSQL_DATABASE` | `stelr` | Database name |
| `MYSQL_POOL_SIZE` | `10` | Max pooled connections |

`MYSQL_FLUSH_LOG_AT_TRX_COMMIT` (default `1`, set on the `mysql` container, not the app) controls
InnoDB's write durability vs. speed. `1` fsyncs on every commit and survives any crash, but is the
slowest. `2` only fsyncs once/sec — writes are much faster, but up to ~1 second of the most recent
adds/deletes can be lost if the *host* (not just MySQL) crashes or loses power. `0` is faster still
but can also lose data on a plain MySQL crash. Example:

```bash
MYSQL_FLUSH_LOG_AT_TRX_COMMIT=2 podman compose --profile mysql up
```

---

### PostgreSQL
Links and users are stored in a PostgreSQL database. Stelr will create the
database and tables automatically on first run.

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
| `POSTGRES_POOL_SIZE`| `10`       | Max pooled connections |

---

## Configuration

| Environment Variable      | Default                  | Description                              |
|---------------------------|--------------------------|------------------------------------------|
| `STORAGE_BACKEND`         | `xml`                    | Storage plugin to use                    |
| `ADMIN_USERNAME`          | `admin`                  | Username for the auto-created admin      |
| `ADMIN_PASSWORD`          | `admin`                  | Password for the auto-created admin      |
| `SECRET_KEY`              | *(default set)*          | Flask session secret — change in production |
| `SESSION_TIMEOUT_MINUTES` | `30`                     | Session inactivity timeout in minutes    |

---

## Starting Stelr

Use the `--profile` flag to select a backend. The app is available at
**http://localhost:8082**.

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

To stop without remo1ving data:

```bash
podman compose --profile yaml stop
```

To stop and remove all data volumes (fresh start):

```bash
podman compose --profile yaml down -v
```

### Changing the admin password or session timeout

```bash
ADMIN_PASSWORD=mysecurepassword SESSION_TIMEOUT_MINUTES=60 podman compose up
```
