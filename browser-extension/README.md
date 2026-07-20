# Stelr Bookmark Sync (browser extension)

Save the current page, sync a specific bookmark folder, or sync your entire
browser bookmark tree to a self-hosted Stelr instance.

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

## Using it

- **Save the current page** — click the extension icon, adjust the title,
  rank, or group if you like, and click **Save to Stelr**.
- **Sync a bookmark folder** — in Settings, choose "Sync a specific bookmark
  folder", pick the folder, save, then click **Sync Now**.
- **Sync everything** — choose "Sync all bookmarks" instead.
- **Automatic sync** — set a non-zero interval (minutes) in Settings to sync
  in the background on a timer, in addition to the manual **Sync Now**
  button.

Each top-level folder becomes a Stelr group of the same name (auto-created
if it doesn't exist yet). Sync only **adds and updates** links — deleting a
bookmark in your browser does not delete the corresponding Stelr link.
Re-running sync is safe: previously-synced bookmarks are matched and
updated in place rather than duplicated.

## Notes

- Manifest V3, using `chrome.*` APIs (Chrome/Edge). Firefox 109+ also
  supports MV3 with `browser.*`/`chrome.*` interchangeably for the APIs
  this extension uses, but hasn't been tested there — file an issue if
  something doesn't work.
- No host permissions are requested upfront. The extension asks for access
  to your specific server only, at login time.
