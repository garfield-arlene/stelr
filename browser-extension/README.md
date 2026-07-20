# Stelr Bookmark Sync (browser extension)

Save the current page, sync a specific bookmark folder, or sync your entire
browser bookmark tree to a self-hosted Stelr instance — one-way (browser →
Stelr) by default, with optional two-way sync and deletion propagation.

## Loading it (development / unpacked)

**Chrome / Edge**
1. Go to `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select this `browser-extension/` folder.

**Firefox**
1. Go to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on** and select `manifest.json` in this folder.
   (Temporary add-ons are removed when Firefox restarts — fine for testing,
   but Firefox needs its own signed/packaged build for real installs.)

## Setting it up

1. Click the extension icon → **Open Settings** (or right-click the icon →
   **Options**).
2. Enter your Stelr server URL, username, and password, and click **Log In**.
   This exchanges your credentials for an API token once — Stelr issues a
   long-lived token, revocable any time from the server's **API Tokens**
   panel or this extension's Settings page — your password itself is never
   stored.
3. The browser will ask permission to let the extension talk to that
   specific server (nothing broader). Allow it.
4. If your server address uses plain `http://` and isn't `localhost`, the
   extension warns you before connecting — your username, password, and API
   token would otherwise cross the network unencrypted. Only continue if you
   trust the network path (e.g. your own LAN).

## Using it

- **Save the current page** — click the extension icon, adjust the title,
  rank, or group if you like, and click **Save to Stelr**.
- **Sync a bookmark folder** — in Settings, choose "Sync a specific bookmark
  folder", pick the folder, save, then click **Sync Now**.
- **Sync everything** — choose "Sync all bookmarks" instead.
- **Two-way sync** — enable "Two-way sync" in Settings to also pull
  Stelr-only links into the browser. Pulled links land in a group-named
  subfolder inside a dedicated **Stelr Sync** folder (full-sync mode), or
  directly inside the chosen folder (folder-sync mode).
- **Propagate deletions** — enable "Propagate deletions" in Settings so
  deleting a bookmark on either side deletes it on the other, next sync.
  Only items this extension has already synced are eligible, and a browser
  bookmark is only treated as deleted once it's confirmed gone entirely (not
  just moved out of the current sync scope, e.g. after switching folders).
- **Automatic sync** — set a non-zero interval (minutes) in Settings to sync
  in the background on a timer, in addition to the manual **Sync Now**
  button.

Each top-level folder becomes a Stelr group of the same name (auto-created
if it doesn't exist yet). By default sync only **adds and updates** links in
one direction (browser → Stelr) and never deletes anything — turn on
two-way sync and/or deletion propagation above to change that. Re-running
sync is safe: previously-synced bookmarks are matched and updated in place
rather than duplicated.

## Notes

- Manifest V3, using the promise-based `browser.*` API (via Mozilla's
  official `webextension-polyfill`, vendored in `lib/browser-polyfill.js`),
  so the same code runs unmodified on Chrome, Edge, and Firefox 109+. The
  manifest declares both `background.service_worker` (Chrome/Edge/modern
  Firefox) and `background.scripts` (older Firefox MV3) plus a
  `browser_specific_settings.gecko.id`, all needed for Firefox to load it.
- No host permissions are requested upfront. The extension asks for access
  to your specific server only, at login time.
- **Firefox and private-network servers**: if your Stelr instance is on a
  plain-HTTP LAN address (e.g. `http://192.168.x.x:5000`, a typical
  self-hosted setup) and login fails with "NetworkError when attempting to
  fetch resource," this is usually Firefox's **Local Network Access**
  protection (rolling out by default from Firefox 151 on) blocking the
  connection — it requires its own native permission prompt, separate from
  the extension's host-permission prompt. Look for that prompt, or check
  Firefox Settings → Privacy & Security → Permissions → Local Network Access.
  This is a browser-level restriction the extension can't bypass; serving
  Stelr over HTTPS avoids it.
