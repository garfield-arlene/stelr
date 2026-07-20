import { runSync } from "./lib/sync-engine.js";

const ALARM_NAME = "stelr-periodic-sync";

// Listener must be registered synchronously at top level so the service
// worker wakes up correctly to handle messages/alarms after termination.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "SYNC_NOW") {
    runSync()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true; // keep the message channel open for the async sendResponse
  }
  return false;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    runSync().catch(() => {});
  }
});
