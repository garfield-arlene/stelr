import "./lib/browser-polyfill.js";
import { runSync } from "./lib/sync-engine.js";

const ALARM_NAME = "stelr-periodic-sync";

// Listener must be registered synchronously at top level so the service
// worker wakes up correctly to handle messages/alarms after termination.
browser.runtime.onMessage.addListener((message) => {
  if (message && message.type === "SYNC_NOW") {
    return runSync()
      .then((result) => ({ ok: true, result }))
      .catch((err) => ({ ok: false, error: err.message }));
  }
  return undefined;
});

browser.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    runSync().catch(() => {});
  }
});
