import * as api from "./lib/stelr-api.js";
import { getSyncConfig, setSyncConfig, listBookmarkFolders } from "./lib/sync-engine.js";

const ALARM_NAME = "stelr-periodic-sync";

const els = {
  loggedOutView: document.getElementById("logged-out-view"),
  loggedInView: document.getElementById("logged-in-view"),
  connectedBadge: document.getElementById("connected-badge"),
  serverInput: document.getElementById("server-input"),
  usernameInput: document.getElementById("username-input"),
  passwordInput: document.getElementById("password-input"),
  loginBtn: document.getElementById("login-btn"),
  logoutBtn: document.getElementById("logout-btn"),
  loginStatus: document.getElementById("login-status"),
  insecureWarning: document.getElementById("insecure-warning"),
  insecureAckInput: document.getElementById("insecure-ack-input"),
  insecureContinueBtn: document.getElementById("insecure-continue-btn"),
  insecureCancelBtn: document.getElementById("insecure-cancel-btn"),
  syncPanel: document.getElementById("sync-panel"),
  folderRow: document.getElementById("folder-row"),
  folderSelect: document.getElementById("folder-select"),
  bidirectionalInput: document.getElementById("bidirectional-input"),
  propagateDeletesInput: document.getElementById("propagate-deletes-input"),
  intervalInput: document.getElementById("interval-input"),
  saveBtn: document.getElementById("save-btn"),
  syncNowBtn: document.getElementById("sync-now-btn"),
  syncStatus: document.getElementById("sync-status"),
};

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

async function refreshFolders() {
  const folders = await listBookmarkFolders();
  els.folderSelect.innerHTML = "";
  for (const f of folders) {
    const opt = document.createElement("option");
    opt.value = f.id;
    opt.textContent = "  ".repeat(f.depth) + f.title;
    els.folderSelect.appendChild(opt);
  }
}

async function render() {
  const config = await api.getConfig();
  if (config) {
    els.loggedOutView.style.display = "none";
    els.loggedInView.style.display = "block";
    els.connectedBadge.textContent = `Connected to ${config.server} as ${config.username}`;
    els.syncPanel.style.display = "block";
    await refreshFolders();

    const syncCfg = await getSyncConfig();
    document.getElementById(`mode-${syncCfg.mode}`).checked = true;
    els.folderRow.classList.toggle("visible", syncCfg.mode === "folder");
    if (syncCfg.folderId) els.folderSelect.value = syncCfg.folderId;
    els.bidirectionalInput.checked = !!syncCfg.bidirectional;
    els.propagateDeletesInput.checked = !!syncCfg.propagateDeletes;
    els.intervalInput.value = syncCfg.periodicMinutes || 0;

    if (syncCfg.lastResult) {
      const r = syncCfg.lastResult;
      const parts = [`${r.created} added`, `${r.updated} updated`, `${r.unchanged} unchanged`];
      if (r.pulled) parts.push(`${r.pulled} pulled`);
      if (r.removedFromStelr) parts.push(`${r.removedFromStelr} deleted from Stelr`);
      if (r.removedFromBrowser) parts.push(`${r.removedFromBrowser} deleted from browser`);
      if (r.errors) parts.push(`${r.errors} errors`);
      setStatus(els.syncStatus,
        `Last sync (${new Date(r.at).toLocaleString()}): ${parts.join(", ")}.`,
        r.errors ? "error" : "success");
    }
  } else {
    els.loggedOutView.style.display = "block";
    els.loggedInView.style.display = "none";
    els.syncPanel.style.display = "none";
  }
}

function hideInsecureWarning() {
  els.insecureWarning.classList.remove("visible");
  els.insecureAckInput.checked = false;
  els.insecureContinueBtn.disabled = true;
}

async function doLogin() {
  setStatus(els.loginStatus, "Logging in…", "");
  try {
    await api.login(
      els.serverInput.value.trim(),
      els.usernameInput.value.trim(),
      els.passwordInput.value,
      "browser-extension"
    );
    els.passwordInput.value = "";
    setStatus(els.loginStatus, "", "");
    hideInsecureWarning();
    await render();
  } catch (e) {
    setStatus(els.loginStatus, e.message, "error");
  }
}

els.loginBtn.addEventListener("click", async () => {
  const server = els.serverInput.value.trim();
  if (api.isInsecureServer(server)) {
    // Require explicit, informed consent before any connection is attempted —
    // this is a fresh click/user gesture, so permissions.request() inside a
    // later doLogin() call (triggered by the Continue button) still qualifies.
    els.insecureWarning.classList.add("visible");
    setStatus(els.loginStatus, "", "");
    return;
  }
  await doLogin();
});

els.insecureAckInput.addEventListener("change", () => {
  els.insecureContinueBtn.disabled = !els.insecureAckInput.checked;
});

els.insecureContinueBtn.addEventListener("click", async () => {
  if (!els.insecureAckInput.checked) return;
  els.insecureWarning.classList.remove("visible");
  await doLogin();
});

els.insecureCancelBtn.addEventListener("click", () => {
  hideInsecureWarning();
});

els.serverInput.addEventListener("input", () => {
  hideInsecureWarning();
});

els.logoutBtn.addEventListener("click", async () => {
  await api.logout();
  await browser.alarms.clear(ALARM_NAME);
  await render();
});

for (const radio of document.querySelectorAll('input[name="sync-mode"]')) {
  radio.addEventListener("change", () => {
    els.folderRow.classList.toggle("visible", radio.value === "folder" && radio.checked);
  });
}

els.saveBtn.addEventListener("click", async () => {
  const mode = document.querySelector('input[name="sync-mode"]:checked').value;
  const folderId = mode === "folder" ? els.folderSelect.value : null;
  const bidirectional = els.bidirectionalInput.checked;
  const propagateDeletes = els.propagateDeletesInput.checked;
  const periodicMinutes = Math.max(0, parseInt(els.intervalInput.value, 10) || 0);

  await setSyncConfig({ mode, folderId, bidirectional, propagateDeletes, periodicMinutes });

  await browser.alarms.clear(ALARM_NAME);
  if (mode !== "off" && periodicMinutes > 0) {
    browser.alarms.create(ALARM_NAME, { periodInMinutes: periodicMinutes });
  }

  setStatus(els.syncStatus, "Settings saved.", "success");
});

els.syncNowBtn.addEventListener("click", async () => {
  setStatus(els.syncStatus, "Syncing…", "");
  const response = await browser.runtime.sendMessage({ type: "SYNC_NOW" });
  if (!response.ok) {
    setStatus(els.syncStatus, response.error, "error");
    return;
  }
  if (response.result.skipped) {
    setStatus(els.syncStatus, "Sync mode is off — nothing to do.", "");
    return;
  }
  await render();
});

render();
