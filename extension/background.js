const SERVER = "http://127.0.0.1:8765";

function reloadOpenGooglePhotosTabs() {
  chrome.tabs.query({ url: ["https://photos.google.com/*"] }, (tabs) => {
    if (chrome.runtime.lastError) return;
    tabs.forEach((tab) => {
      if (!Number.isInteger(tab.id)) return;
      chrome.tabs.reload(tab.id, () => {
        // Recargar una pestaña puede fallar si el usuario la cerró justo antes.
        void chrome.runtime.lastError;
      });
    });
  });
}

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install" || details.reason === "update") {
    reloadOpenGooglePhotosTabs();
  }
});

async function post(path, payload) {
  const response = await fetch(`${SERVER}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Photo Swipper Filter respondió ${response.status}.`);
  }
  return response.json();
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !message || typeof message !== "object") {
    return false;
  }

  let request;
  if (message.type === "swipeclean:heartbeat") {
    request = post("/api/extension/heartbeat", {
      version: chrome.runtime.getManifest().version,
    });
  } else if (message.type === "swipeclean:record") {
    request = post("/api/extension/decisions", message.payload || {});
  } else {
    return false;
  }

  request
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
