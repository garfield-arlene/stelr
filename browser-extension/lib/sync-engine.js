// Bookmark -> Stelr sync engine. Shared by the background service worker
// (manual "Sync Now" and periodic alarm-triggered syncs).

import * as api from "./stelr-api.js";

const SYNC_KEY = "stelrSync";

// Dedicated landing folder for links that originate on the Stelr side during
// full-tree two-way sync. There's no single portable "top level" folder id
// across browsers (Chrome's invisible root is "0", Firefox uses GUID-style
// roots), and guessing which of Bookmarks Bar / Other Bookmarks / Mobile
// Bookmarks the user wants new items in would be arbitrary, so pulled links
// always land in this folder (or a subfolder named after their group).
const SYNC_ROOT_TITLE = "Stelr Sync";

const DEFAULT_SYNC = {
  mode: "off",             // "off" | "folder" | "full"
  folderId: null,           // bookmark folder id, only used when mode === "folder"
  periodicMinutes: 0,       // 0 = manual only
  bidirectional: false,     // also pull Stelr-only links into the browser
  propagateDeletes: false,  // deleting on one side deletes on the other
  bookmarkMap: {},           // browserBookmarkId -> { linkId, title, url, groupId }
  lastResult: null,          // { created, updated, unchanged, pulled, removedFromStelr, removedFromBrowser, errors, total, at }
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

/** Find a child folder of parentId with the given title, creating it if absent. */
async function findOrCreateFolder(parentId, title, cache) {
  const cacheKey = `${parentId}::${title}`;
  if (cache.has(cacheKey)) return cache.get(cacheKey);
  const children = await browser.bookmarks.getChildren(parentId);
  const existing = children.find((c) => !c.url && c.title === title);
  const id = existing ? existing.id : (await browser.bookmarks.create({ parentId, title })).id;
  cache.set(cacheKey, id);
  return id;
}

/** Resolve the folder that pulled (Stelr-only) links get created under. */
async function getPullRootId(syncCfg) {
  if (syncCfg.mode === "folder") return syncCfg.folderId;
  const matches = await browser.bookmarks.search({ title: SYNC_ROOT_TITLE });
  const existing = matches.find((n) => !n.url);
  if (existing) return existing.id;
  const [root] = await browser.bookmarks.getTree();
  return (await browser.bookmarks.create({ parentId: root.children[0].id, title: SYNC_ROOT_TITLE })).id;
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
  const localIds = new Set(bookmarks.map((b) => b.id));

  const existingGroups = await api.getGroups();
  const groupIdByName = new Map(existingGroups.map((g) => [g.name, g.id]));
  const groupNameById = new Map(existingGroups.map((g) => [g.id, g.name]));

  const bookmarkMap = { ...syncCfg.bookmarkMap };
  let created = 0, updated = 0, unchanged = 0, errors = 0;
  let pulled = 0, removedFromStelr = 0, removedFromBrowser = 0;

  // Push: browser -> Stelr.
  for (const bm of bookmarks) {
    try {
      let groupId = "";
      if (bm.parentTitle) {
        if (!groupIdByName.has(bm.parentTitle)) {
          const g = await api.createGroup(bm.parentTitle);
          groupIdByName.set(bm.parentTitle, g.id);
          groupNameById.set(g.id, g.name);
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

  // Deletions, browser -> Stelr: a previously-synced browser bookmark that's
  // both missing from this run's collected set AND confirmed gone from the
  // browser entirely (not just out of the current sync scope, e.g. after
  // switching sync folders) was deleted locally, so remove its Stelr link too.
  if (syncCfg.propagateDeletes) {
    for (const [browserId, entry] of Object.entries(bookmarkMap)) {
      if (localIds.has(browserId)) continue;
      try {
        await browser.bookmarks.get(browserId);
        continue; // still exists somewhere in the browser, just out of scope
      } catch (e) {
        // confirmed gone — fall through and propagate the deletion
      }
      try {
        await api.deleteLink(entry.linkId);
      } catch (e) {
        // already gone server-side, or a transient error; stop tracking it
        // either way so we don't retry forever
      }
      delete bookmarkMap[browserId];
      removedFromStelr++;
    }
  }

  // Pull: Stelr -> browser. Only fetch the full link list when it's actually
  // needed (bidirectional sync and/or remote-delete propagation).
  if (syncCfg.bidirectional || syncCfg.propagateDeletes) {
    const existingLinks = await api.getLinks();
    const linkIds = new Set(existingLinks.map((l) => l.id));
    const trackedLinkIds = new Set(Object.values(bookmarkMap).map((e) => e.linkId));

    if (syncCfg.propagateDeletes) {
      for (const [browserId, entry] of Object.entries(bookmarkMap)) {
        if (linkIds.has(entry.linkId)) continue;
        try {
          await browser.bookmarks.remove(browserId);
        } catch (e) {
          // already gone locally; drop the mapping regardless
        }
        delete bookmarkMap[browserId];
        removedFromBrowser++;
      }
    }

    if (syncCfg.bidirectional) {
      const folderCache = new Map();
      const pullRootId = await getPullRootId(syncCfg);
      for (const link of existingLinks) {
        if (trackedLinkIds.has(link.id)) continue;
        try {
          const groupName = link.group_id ? groupNameById.get(link.group_id) : null;
          const parentId = groupName
            ? await findOrCreateFolder(pullRootId, groupName, folderCache)
            : pullRootId;
          const newBookmark = await browser.bookmarks.create({
            parentId, title: link.title || link.url, url: link.url,
          });
          bookmarkMap[newBookmark.id] = {
            linkId: link.id, title: link.title, url: link.url, groupId: link.group_id || "",
          };
          pulled++;
        } catch (e) {
          errors++;
        }
      }
    }
  }

  const result = {
    created, updated, unchanged, pulled, removedFromStelr, removedFromBrowser, errors,
    total: bookmarks.length, at: new Date().toISOString(),
  };
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
