// Shared Stelr API client used by the popup, options page, and background sync engine.

const CONFIG_KEY = "stelrConfig";

export async function getConfig() {
  const data = await browser.storage.local.get(CONFIG_KEY);
  return data[CONFIG_KEY] || null;
}

export async function setConfig(config) {
  await browser.storage.local.set({ [CONFIG_KEY]: config });
}

export async function clearConfig() {
  await browser.storage.local.remove(CONFIG_KEY);
}

function originPattern(server) {
  return new URL(server).origin + "/*";
}

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"]);

/** True if `server` uses plain HTTP against a non-local host — credentials
 * and the API token would cross the network unencrypted. */
export function isInsecureServer(server) {
  let url;
  try {
    url = new URL(server);
  } catch (e) {
    return false;
  }
  return url.protocol === "http:" && !LOCAL_HOSTNAMES.has(url.hostname);
}

export async function hasHostPermission(server) {
  return browser.permissions.contains({ origins: [originPattern(server)] });
}

export async function requestHostPermission(server) {
  return browser.permissions.request({ origins: [originPattern(server)] });
}

const PRIVATE_IPV4 = /^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|169\.254\.)/;

function isPrivateNetworkHost(hostname) {
  return !LOCAL_HOSTNAMES.has(hostname) && PRIVATE_IPV4.test(hostname);
}

/** Fetch failures that reach here (TypeError, no HTTP response at all) are
 * connection-level, not something the server's response body can explain.
 * The most common unhelpful case in Firefox: its "Local Network Access"
 * protection (rolling out Firefox 151+) silently blocks a request to a
 * private-network address until the user approves a separate native prompt
 * — distinct from the WebExtensions host-permission prompt already granted
 * — so point people at it instead of surfacing the raw "NetworkError". */
function describeFetchError(e, server) {
  // Use e.name rather than `instanceof TypeError` -- fetch() errors can be
  // constructed in a different realm than this module (extension page vs.
  // privileged internals), where instanceof fails even though .name is set
  // correctly, since .name is a plain string property, not identity-based.
  if (e.name !== "TypeError") return e.message;
  let hostname = "";
  try {
    hostname = new URL(server).hostname;
  } catch (err) {
    // leave hostname blank; fall through to the generic message below
  }
  if (isPrivateNetworkHost(hostname)) {
    return `Could not reach ${server}. If you're on Firefox, this is often its ` +
      `"Local Network Access" protection blocking the connection — look for a ` +
      `permission prompt (separate from the earlier one), or check ` +
      `Settings → Privacy & Security → Permissions → Local Network Access. ` +
      `Otherwise, confirm the server is running and the address is correct.`;
  }
  return `Could not reach ${server}. Confirm the server is running and the address is correct.`;
}

export async function login(server, username, password, tokenName) {
  server = server.replace(/\/+$/, "");
  // Must be the very first async operation here (no preceding await), since
  // permissions.request() is only callable from within a live user gesture
  // (the click that triggered this call) — it resolves immediately with no
  // prompt if the origin is already granted, so this stays cheap either way.
  const granted = await requestHostPermission(server);
  if (!granted) {
    throw new Error("Permission to contact that server was not granted.");
  }
  let resp;
  try {
    resp = await fetch(`${server}/api/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, name: tokenName }),
    });
  } catch (e) {
    throw new Error(describeFetchError(e, server));
  }
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
  let resp;
  try {
    resp = await fetch(`${config.server}${path}`, {
      method,
      headers: {
        "Authorization": `Bearer ${config.token}`,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new Error(describeFetchError(e, config.server));
  }
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
