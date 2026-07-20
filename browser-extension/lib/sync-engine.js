// Bookmark -> Stelr sync engine. Shared by the background service worker
// (manual "Sync Now" and periodic alarm-triggered syncs).

import * as api from "./stelr-api.js";

const SYNC_KEY = "stelrSync";

const DEFAULT_SYNC = {
  mode: "off",          // "off" | "folder" | "full"
  folderId: null,        // bookmark folder id, only used when mode === "folder"
  periodicMinutes: 0,    // 0 = manual only
  bookmarkMap: {},        // browserBookmarkId -> { linkId, title, url, groupId }
  lastResult: null,       // { created, updated, errors, total, at }
};

export async function getSyncConfig() {
  const data = await browser.storage.local.get(SYNC_KEY);
  return { ...DEFAULT_SYNC, ...(data[SYNC_KEY] || {}) };
}

export async function setSyncConfig(patch) {
  const current = await getSyncConfig();
  const next = { ...current, ...patch };
  await browser.storage.local.set({ [SYNC_KEY]: next });
  return next;
}

/**
 * Flatten a bookmark subtree into { id, title, url, parentTitle } leaves.
 * Pass a specific folderId to scope to that folder, or omit it to walk the
 * whole tree — root bookmark/folder IDs are not portable across browsers
 * (Chrome uses "0", Firefox uses its own GUID-style roots), so the full-tree
 * case must go through getTree() rather than a hardcoded root ID.
 */
async function collectBookmarks(folderId) {
  const [root] = folderId
    ? await browser.bookmarks.getSubTree(folderId)
    : await browser.bookmarks.getTree();
  const results = [];

  function walk(node, parentTitle) {
    if (!node.children) return;
    for (const child of node.children) {
      if (child.url) {
        results.push({
          id: child.id,
          title: child.title || child.url,
          url: child.url,
          parentTitle,
        });
      } else {
        walk(child, child.title);
      }
    }
  }

  walk(root, root.title);
  return results;
}

export async function runSync() {
  const syncCfg = await getSyncConfig();
  if (syncCfg.mode === "off") {
    return { skipped: true };
  }

  if (syncCfg.mode === "folder" && !syncCfg.folderId) {
    throw new Error("No sync folder selected.");
  }

  const bookmarks = await collectBookmarks(syncCfg.mode === "folder" ? syncCfg.folderId : null);

  const existingGroups = await api.getGroups();
  const groupIdByName = new Map(existingGroups.map((g) => [g.name, g.id]));

  const bookmarkMap = { ...syncCfg.bookmarkMap };
  let created = 0, updated = 0, unchanged = 0, errors = 0;

  for (const bm of bookmarks) {
    try {
      let groupId = "";
      if (bm.parentTitle) {
        if (!groupIdByName.has(bm.parentTitle)) {
          const g = await api.createGroup(bm.parentTitle);
          groupIdByName.set(bm.parentTitle, g.id);
        }
        groupId = groupIdByName.get(bm.parentTitle);
      }

      const existing = bookmarkMap[bm.id];
      if (existing) {
        if (existing.title !== bm.title || existing.url !== bm.url || existing.groupId !== groupId) {
          await api.updateLink(existing.linkId, { title: bm.title, url: bm.url, group_id: groupId });
          updated++;
        } else {
          unchanged++;
        }
        bookmarkMap[bm.id] = { linkId: existing.linkId, title: bm.title, url: bm.url, groupId };
      } else {
        const link = await api.createLink({ title: bm.title, url: bm.url, group_id: groupId });
        bookmarkMap[bm.id] = { linkId: link.id, title: bm.title, url: bm.url, groupId };
        created++;
      }
    } catch (e) {
      errors++;
    }
  }

  const result = { created, updated, unchanged, errors, total: bookmarks.length, at: new Date().toISOString() };
  await setSyncConfig({ bookmarkMap, lastResult: result });
  return result;
}

export async function listBookmarkFolders() {
  const [root] = await browser.bookmarks.getTree();
  const folders = [];

  function walk(node, depth) {
    if (node.children === undefined) return;
    if (node.title) {
      folders.push({ id: node.id, title: node.title, depth });
    }
    for (const child of node.children) {
      walk(child, depth + 1);
    }
  }

  for (const child of root.children || []) {
    walk(child, 0);
  }
  return folders;
}
