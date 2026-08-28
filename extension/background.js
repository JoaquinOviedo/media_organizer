const SERVER = "http://127.0.0.1:8765";

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
