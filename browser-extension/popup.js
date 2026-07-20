import * as api from "./lib/stelr-api.js";

const els = {
  loggedInView: document.getElementById("logged-in-view"),
  loggedOutView: document.getElementById("logged-out-view"),
  openSettingsBtn: document.getElementById("open-settings-btn"),
  titleInput: document.getElementById("title-input"),
  urlInput: document.getElementById("url-input"),
  rankInput: document.getElementById("rank-input"),
  groupSelect: document.getElementById("group-select"),
  saveBtn: document.getElementById("save-btn"),
  saveStatus: document.getElementById("save-status"),
  syncNowBtn: document.getElementById("sync-now-btn"),
  syncStatus: document.getElementById("sync-status"),
};

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

els.openSettingsBtn.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

async function init() {
  const config = await api.getConfig();
  if (!config) {
    els.loggedInView.style.display = "none";
    els.loggedOutView.style.display = "block";
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    els.titleInput.value = tab.title || "";
    els.urlInput.value = tab.url || "";
  }

  try {
    const groups = await api.getGroups();
    for (const g of groups) {
      const opt = document.createElement("option");
      opt.value = g.id;
      opt.textContent = g.name;
      els.groupSelect.appendChild(opt);
    }
  } catch (e) {
    // groups are a nice-to-have; saving still works without them
  }
}

els.saveBtn.addEventListener("click", async () => {
  const title = els.titleInput.value.trim();
  const url = els.urlInput.value.trim();
  if (!title || !url) {
    setStatus(els.saveStatus, "Title and URL are required.", "error");
    return;
  }
  setStatus(els.saveStatus, "Saving…", "");
  try {
    await api.createLink({
      title,
      url,
      rank: parseInt(els.rankInput.value, 10) || 0,
      group_id: els.groupSelect.value,
    });
    setStatus(els.saveStatus, "Saved!", "success");
  } catch (e) {
    setStatus(els.saveStatus, e.message, "error");
  }
});

els.syncNowBtn.addEventListener("click", async () => {
  setStatus(els.syncStatus, "Syncing…", "");
  const response = await chrome.runtime.sendMessage({ type: "SYNC_NOW" });
  if (!response.ok) {
    setStatus(els.syncStatus, response.error, "error");
    return;
  }
  if (response.result.skipped) {
    setStatus(els.syncStatus, "Sync mode is off (see Settings).", "");
    return;
  }
  const r = response.result;
  setStatus(els.syncStatus,
    `${r.created} added, ${r.updated} updated` + (r.errors ? `, ${r.errors} errors` : "") + ".",
    r.errors ? "error" : "success");
});

init();
