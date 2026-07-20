// Shared Stelr API client used by the popup, options page, and background sync engine.

const CONFIG_KEY = "stelrConfig";

export async function getConfig() {
  const data = await chrome.storage.local.get(CONFIG_KEY);
  return data[CONFIG_KEY] || null;
}

export async function setConfig(config) {
  await chrome.storage.local.set({ [CONFIG_KEY]: config });
}

export async function clearConfig() {
  await chrome.storage.local.remove(CONFIG_KEY);
}

function originPattern(server) {
  return new URL(server).origin + "/*";
}

export async function hasHostPermission(server) {
  return chrome.permissions.contains({ origins: [originPattern(server)] });
}

export async function requestHostPermission(server) {
  return chrome.permissions.request({ origins: [originPattern(server)] });
}

export async function login(server, username, password, tokenName) {
  server = server.replace(/\/+$/, "");
  const granted = (await hasHostPermission(server)) || (await requestHostPermission(server));
  if (!granted) {
    throw new Error("Permission to contact that server was not granted.");
  }
  const resp = await fetch(`${server}/api/tokens`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, name: tokenName }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || `Login failed (HTTP ${resp.status})`);
  }
  await setConfig({ server, token: data.token, tokenId: data.id, username });
  return data;
}

export async function logout() {
  const config = await getConfig();
  if (config) {
    try {
      await apiRequest("DELETE", `/api/tokens/${config.tokenId}`);
    } catch (e) {
      // best-effort revoke; local config is cleared regardless
    }
  }
  await clearConfig();
}

export async function apiRequest(method, path, body) {
  const config = await getConfig();
  if (!config) throw new Error("Not logged in.");
  const resp = await fetch(`${config.server}${path}`, {
    method,
    headers: {
      "Authorization": `Bearer ${config.token}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    // no/invalid JSON body (e.g. 204-style responses); leave data as null
  }
  if (!resp.ok) {
    throw new Error((data && data.error) || `Request failed (HTTP ${resp.status})`);
  }
  return data;
}

export const getLinks = (params) =>
  apiRequest("GET", `/api/links${params ? "?" + new URLSearchParams(params).toString() : ""}`);
export const createLink = (link) => apiRequest("POST", "/api/links", link);
export const updateLink = (id, link) => apiRequest("PUT", `/api/links/${encodeURIComponent(id)}`, link);
export const deleteLink = (id) => apiRequest("DELETE", `/api/links/${encodeURIComponent(id)}`);
export const getGroups = () => apiRequest("GET", "/api/groups");
export const createGroup = (name) => apiRequest("POST", "/api/groups", { name });
