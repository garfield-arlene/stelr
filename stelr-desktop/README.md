# Stelr Desktop

A native desktop client for Stelr, built with [Fyne](https://fyne.io). Log in
with your username and password, then search, add, edit, delete, and open
your saved links — the same [REST API](../README.md#rest-api) the CLI and
browser extension use.

Licensed under [AGPL-3.0](../LICENSE), same as the rest of the Stelr project.

## Building and running

Requires Go 1.22+ and a C compiler (Fyne uses cgo for OpenGL bindings) — see
[Fyne's getting started guide](https://docs.fyne.io/started/) for
platform-specific prerequisites.

```bash
cd stelr-desktop
go run .
```

To build a standalone binary:

```bash
go build -o stelr-desktop .
```

## Using it

1. Enter your **Stelr Server URL**, **Username**, and **Password**, then click
   **Connect**. This exchanges your credentials for an API token, the same
   way the [CLI](../README.md#cli-tool) does — your password itself isn't
   stored anywhere.
2. Your links load automatically on connect. Use the search bar to filter by
   title or URL, or **Clear** to reset.
3. Select a link in the list to load it into the **Title**/**URL**/**Rank**
   fields above, then use **Open Bookmark**, **Edit Bookmark**, or **Delete
   bookmark**.
4. Fill in **Title**, **URL**, and **Rank** and click **Add Bookmark** to
   create a new link.

## Notes

- The API token is held in memory only for the current session — nothing is
  written to disk, so you'll need to log in again each time you start the
  app.
- No warning is currently shown when connecting to a plain-HTTP,
  non-localhost server (unlike the browser extension) — avoid pointing this
  at a server outside a network you trust until that's added.
- Deletes happen immediately with no confirmation prompt.
