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

## Running a downloaded Linux build

The Linux release tarball (`Stelr-desktop-*-linux-*.tar.gz`) extracts to a
`usr/local/...`-shaped layout, not a single ready-to-run folder:

```
usr/local/bin/stelr-desktop
usr/local/share/pixmaps/com.stelr.desktop.png
usr/local/share/applications/com.stelr.desktop.desktop
Makefile
```

**Just want to run it?** Extract the tarball and run the binary directly —
`./usr/local/bin/stelr-desktop` — no further setup needed. It won't have an
icon in your taskbar/app switcher this way, since that comes from the
`.desktop` file below, not the binary itself.

**Want the icon and an app-launcher entry?** Install it with the bundled
`Makefile`, which requires `make` (not always preinstalled on a fresh
Linux desktop — e.g. `sudo dnf install make` on Fedora, `sudo apt install
make` on Debian/Ubuntu):

```bash
tar -xzf Stelr-desktop-*-linux-*.tar.gz
cd stelr-desktop
make user-install     # installs to ~/.local, no sudo needed
```

Then launch it from your application launcher rather than the raw binary,
so the desktop environment picks up the icon. `make user-uninstall` reverses
it; `sudo make install`/`sudo make uninstall` do the same system-wide.

macOS and Windows builds don't have this extra step — the macOS `.zip`
contains a ready `.app` bundle, and the Windows `.exe` has its icon
embedded directly.

## Installing via Flatpak (Linux)

As an alternative to the tarball above, a native Flatpak package
(`stelr-desktop-*.flatpak`) is built from [`flatpak/com.stelr.desktop.yml`](flatpak/com.stelr.desktop.yml).
It installs the icon, `.desktop` file, and AppStream metadata automatically —
no `make install` step needed:

```bash
flatpak install --user --bundle stelr-desktop-*.flatpak
```

Launch it from your application launcher, or `flatpak run com.stelr.desktop`.
Uninstall with `flatpak uninstall com.stelr.desktop`.

## Using it

1. Enter your **Stelr Server URL**, **Username**, and **Password**, then click
   **Connect**. This exchanges your credentials for an API token, the same
   way the [CLI](../README.md#cli-tool) does — your password itself isn't
   stored anywhere.
2. Your links (and groups) load automatically on connect. Use the search bar
   to filter by title or URL, or **Clear** to reset.
3. Select a link in the list to load it into the **Title**/**URL**/**Rank**
   fields above, then use **Open Bookmark**, **Edit Bookmark**, or **Delete
   bookmark**.
4. Fill in **Title**, **URL**, and **Rank**, pick a **Group** (or leave it
   "No Group"), and click **Add Bookmark** to create a new link.
5. Use the group filter dropdown above the search results to narrow the list
   to "All Groups", "Ungrouped", or a specific group. Use the **Groups**
   panel's **New Group** field and **Create Group** button to add a group.

## Notes

- The API token is held in memory only for the current session — nothing is
  written to disk, so you'll need to log in again each time you start the
  app.
- Connecting to a plain-HTTP, non-localhost server shows a warning before
  continuing, since credentials and the API token would otherwise cross the
  network unencrypted — same protection as the browser extension.
- Deleting a bookmark asks for confirmation first.
- The window title and a **Version** label in the Groups panel show the
  app's version, embedded at build time.
- If groups can't be fetched (e.g. an older Stelr server without group
  support), Connect still succeeds with an empty group list rather than
  failing outright — a status message calls out the degraded state.
