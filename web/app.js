const state = {
  items: [],
  history: [],
  folder: null,
  dragStartX: null,
  renderedItemId: null,
  decisionInFlight: false,
  preloadedImages: new Map(),
  extensionPath: "",
  destinationFolders: [],
  selectedDestination: null,
};

const $ = (id) => document.getElementById(id);
const card = $("card");
const MEDIA_LAYOUT_CLASSES = ["media-landscape", "media-portrait", "media-square", "media-audio"];

function setMediaLayout(width, height, kind = "visual") {
  card.classList.remove(...MEDIA_LAYOUT_CLASSES);
  if (kind === "audio") {
    card.classList.add("media-audio");
    return;
  }

  const safeWidth = Number(width || 0);
  const safeHeight = Number(height || 0);
  if (safeWidth <= 0 || safeHeight <= 0) {
    card.classList.add("media-landscape");
    return;
  }

  const ratio = safeWidth / safeHeight;
  if (ratio < 0.9) card.classList.add("media-portrait");
  else if (ratio > 1.1) card.classList.add("media-landscape");
  else card.classList.add("media-square");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const contentType = response.headers.get("Content-Type") || "";
  const payload = response.status === 204
    ? {}
    : contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() };
  if (!response.ok) throw new Error(payload.error || "Ocurrió un error inesperado.");
  return payload;
}

function toast(message, duration = 3600) {
  const element = $("toast");
  element.textContent = message;
  element.classList.remove("hidden");
  window.setTimeout(() => element.classList.add("hidden"), duration);
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && size >= 1024; index += 1) {
    size /= 1024;
    unit = units[index];
  }
  return `${size >= 10 ? size.toFixed(0) : size.toFixed(1)} ${unit}`;
}

function mediaKind(item) {
  if (item?.type === "VIDEO") return "Video";
  if (item?.type === "AUDIO") return "Audio";
  return "Foto";
}

function contentUrl(item) {
  return `/api/local/media/${encodeURIComponent(item.item_id)}/content?v=${encodeURIComponent(item.modified_at || 0)}`;
}

function currentItem() {
  return state.items.find((item) => item.decision === "pending") || null;
}

function stopPlayers() {
  for (const id of ["mediaVideo", "mediaAudio"]) {
    const player = $(id);
    player.pause();
    player.removeAttribute("src");
    player.load();
  }
}

function clearMedia() {
  stopPlayers();
  card.classList.remove(...MEDIA_LAYOUT_CLASSES);
  const image = $("mediaImage");
  image.removeAttribute("src");
  image.classList.add("hidden");
  $("mediaVideo").classList.add("hidden");
  $("audioStage").classList.add("hidden");
}

function showMedia(item) {
  clearMedia();
  card.classList.add("loading");
  card.classList.toggle("video-mode", item.type === "VIDEO" || item.type === "AUDIO");
  const url = contentUrl(item);

  if (item.type === "VIDEO") {
    const video = $("mediaVideo");
    setMediaLayout(16, 9);
    video.classList.remove("hidden");
    video.onloadedmetadata = () => setMediaLayout(video.videoWidth, video.videoHeight);
    video.onloadeddata = () => {
      setMediaLayout(video.videoWidth, video.videoHeight);
      card.classList.remove("loading");
    };
    video.onerror = () => {
      card.classList.remove("loading");
      toast("El navegador no pudo reproducir este formato de video.");
    };
    video.src = url;
    video.load();
  } else if (item.type === "AUDIO") {
    const audio = $("mediaAudio");
    setMediaLayout(1, 1, "audio");
    $("audioStage").classList.remove("hidden");
    $("audioName").textContent = item.filename;
    audio.onloadedmetadata = () => card.classList.remove("loading");
    audio.onerror = () => {
      card.classList.remove("loading");
      toast("El navegador no pudo reproducir este formato de audio.");
    };
    audio.src = url;
    audio.load();
  } else {
    const image = $("mediaImage");
    setMediaLayout(4, 3);
    image.classList.remove("hidden");
    image.alt = item.filename || "Foto local";
    image.onload = () => {
      setMediaLayout(image.naturalWidth, image.naturalHeight);
      card.classList.remove("loading");
    };
    image.onerror = () => {
      card.classList.remove("loading");
      toast("No se pudo previsualizar esta imagen.");
    };
    image.src = url;
    if (image.complete && image.naturalWidth > 0) {
      setMediaLayout(image.naturalWidth, image.naturalHeight);
      card.classList.remove("loading");
    }
  }
  state.renderedItemId = item.item_id;
}

function preloadFollowing(current) {
  const index = state.items.findIndex((item) => item.item_id === current?.item_id);
  if (index < 0) return;
  const following = state.items
    .slice(index + 1)
    .filter((item) => item.decision === "pending" && item.type === "IMAGE")
    .slice(0, 3);
  for (const item of following) {
    if (state.preloadedImages.has(item.item_id)) continue;
    const image = new Image();
    image.decoding = "async";
    image.src = contentUrl(item);
    state.preloadedImages.set(item.item_id, image);
  }
  while (state.preloadedImages.size > 8) {
    state.preloadedImages.delete(state.preloadedImages.keys().next().value);
  }
}

function renderMovedQueue() {
  const moved = state.items.filter((item) => item.decision === "delete");
  const root = $("movedQueue");
  root.replaceChildren();
  if (!moved.length) {
    root.textContent = "Todavía no moviste archivos.";
    return;
  }
  for (const item of moved.slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "local-delete-item";
    const name = document.createElement("strong");
    name.textContent = item.filename;
    const detail = document.createElement("span");
    detail.textContent = `${mediaKind(item)} · ${formatBytes(item.size_bytes)} · ${item.original_relative_path}`;
    row.append(name, detail);
    root.appendChild(row);
  }
  if (moved.length > 12) {
    const remaining = document.createElement("p");
    remaining.textContent = `y ${moved.length - 12} archivos más…`;
    root.appendChild(remaining);
  }
}

function renderFolderStatus() {
  const folder = state.folder;
  const selected = Boolean(folder?.selected);
  $("folderBadge").textContent = selected ? `${folder.total} archivos encontrados` : "Sin carpeta elegida";
  $("folderBadge").classList.toggle("connected", selected);
  $("rootPath").classList.toggle("hidden", !selected);
  $("rescanFolderButton").classList.toggle("hidden", !selected);
  $("organizePanel").classList.toggle("hidden", !selected);
  $("rootPath").textContent = folder?.rootPath || "";
  $("discardPath").textContent = folder?.discardPath || "Elegí una carpeta para ver el destino.";
  $("folderCopy").textContent = selected
    ? "La carpeta y todas sus subcarpetas están listas para revisar."
    : "También vamos a revisar automáticamente sus subcarpetas, sin subir ningún archivo a internet.";
}

function renderDestinationFolders() {
  const select = $("destinationFolderSelect");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = state.destinationFolders.length
    ? "Elegir otra carpeta…"
    : "Primero creá una carpeta…";
  select.replaceChildren(placeholder);
  for (const folder of state.destinationFolders) {
    const option = document.createElement("option");
    option.value = folder.relativePath;
    option.textContent = folder.name;
    select.appendChild(option);
  }
  select.value = state.selectedDestination || "";

  const selected = state.destinationFolders.find(
    (folder) => folder.relativePath === state.selectedDestination,
  );
  $("selectedDestinationLabel").textContent = selected
    ? `↑ ${selected.name}`
    : "Todavía no elegiste una carpeta";
  $("destinationHelp").textContent = selected
    ? `Las próximas fotos que marques con ↑ se moverán a “${selected.name}”.`
    : "Creá una carpeta o elegí una de la lista. La selección queda guardada para las próximas fotos.";
  $("organizeButtonDestination").textContent = selected
    ? `mover a ${selected.name}`
    : "elegí una carpeta arriba";
  $("organizePanel").classList.toggle("destination-selected", Boolean(selected));
}

function render() {
  const counts = { pending: 0, keep: 0, delete: 0, organize: 0 };
  state.items.forEach((item) => { counts[item.decision] = (counts[item.decision] || 0) + 1; });
  Object.entries(counts).forEach(([key, value]) => $(`${key}Count`).textContent = value);
  renderFolderStatus();
  renderDestinationFolders();
  renderMovedQueue();

  const item = currentItem();
  $("emptyState").classList.toggle("hidden", Boolean(item));
  $("controlsBar").classList.toggle("hidden", !item && state.history.length === 0);
  $("keyboardHelp").classList.toggle("hidden", !item && state.history.length === 0);
  card.classList.toggle("hidden", !item);
  if (item) {
    if (state.renderedItemId !== item.item_id) showMedia(item);
    $("mediaName").textContent = item.filename;
    const date = item.modified_at ? new Date(item.modified_at * 1000).toLocaleString() : "Sin fecha";
    $("mediaDetail").textContent = `${mediaKind(item)} · ${formatBytes(item.size_bytes)} · ${date}`;
    $("mediaRelativePath").textContent = item.original_relative_path;
    preloadFollowing(item);
  } else {
    state.renderedItemId = null;
    clearMedia();
    const heading = $("emptyState").querySelector("h2");
    const copy = $("emptyState").querySelector("p");
    if (!state.folder?.selected) {
      heading.textContent = "Primero explorá una carpeta";
      copy.textContent = "Después vas a poder mirar imágenes, videos y audios uno por uno.";
    } else if (state.items.length === 0) {
      heading.textContent = "No encontramos archivos compatibles";
      copy.textContent = "Probá con otra carpeta o volvé a escanear después de agregar archivos.";
    } else {
      heading.textContent = "Revisión terminada";
      copy.textContent = "Todos los archivos tienen una decisión.";
    }
  }
  $("undoButton").disabled = state.history.length === 0 || state.decisionInFlight;
  $("deleteButton").disabled = !item || state.decisionInFlight;
  $("keepButton").disabled = !item || state.decisionInFlight;
  $("printButton").disabled = !item || item.type !== "IMAGE" || state.decisionInFlight;
  $("organizeButton").disabled = !item || !state.selectedDestination || state.decisionInFlight;
}

async function loadLocalLibrary() {
  const [folder, payload, destinations] = await Promise.all([
    api("/api/local/status"),
    api("/api/local/media"),
    api("/api/local/organize-folders"),
  ]);
  state.folder = folder;
  state.items = payload.items;
  state.destinationFolders = destinations.folders;
  state.selectedDestination = destinations.selected;
  state.renderedItemId = null;
  render();
}

async function createDestinationFolder() {
  const input = $("newFolderName");
  const button = $("createDestinationFolderButton");
  const name = input.value.trim();
  if (!name) {
    toast("Escribí el nombre de la carpeta que querés crear.");
    input.focus();
    return;
  }
  button.disabled = true;
  button.textContent = "Creando…";
  try {
    const result = await api("/api/local/organize-folders", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    state.destinationFolders = result.folders;
    state.selectedDestination = result.selected;
    input.value = "";
    render();
    toast(`Carpeta “${name}” creada y seleccionada.`);
  } catch (error) {
    toast(error.message, 5200);
  } finally {
    button.disabled = false;
    button.textContent = "Crear y usar";
  }
}

async function selectDestinationFolder(relativePath) {
  if (!relativePath) {
    renderDestinationFolders();
    return;
  }
  const select = $("destinationFolderSelect");
  select.disabled = true;
  try {
    const result = await api("/api/local/organize-folders/select", {
      method: "POST",
      body: JSON.stringify({ relativePath }),
    });
    state.destinationFolders = result.folders;
    state.selectedDestination = result.selected;
    render();
    const selected = state.destinationFolders.find((folder) => folder.relativePath === result.selected);
    toast(`Ahora la flecha ↑ mueve a “${selected?.name || relativePath}”.`);
  } catch (error) {
    renderDestinationFolders();
    toast(error.message, 5200);
  } finally {
    select.disabled = false;
  }
}

async function chooseLocalFolder() {
  const button = $("selectFolderButton");
  button.disabled = true;
  button.textContent = "Esperando selección…";
  try {
    const result = await api("/api/local/folder/select", { method: "POST", body: "{}" });
    if (result.cancelled) return;
    state.history = [];
    state.preloadedImages.clear();
    await loadLocalLibrary();
    toast(`${result.total} archivos listos para revisar.`);
  } catch (error) {
    toast(error.message, 5200);
  } finally {
    button.disabled = false;
    button.textContent = "📁 Explorar carpetas";
  }
}

async function rescanLocalFolder() {
  const button = $("rescanFolderButton");
  button.disabled = true;
  button.textContent = "Escaneando…";
  try {
    const result = await api("/api/local/folder/rescan", { method: "POST", body: "{}" });
    state.preloadedImages.clear();
    await loadLocalLibrary();
    toast(`${result.total} archivos encontrados.`);
  } catch (error) {
    toast(error.message, 5200);
  } finally {
    button.disabled = false;
    button.textContent = "Buscar archivos nuevos";
  }
}

function replaceItem(updated) {
  const index = state.items.findIndex((item) => item.item_id === updated.item_id);
  if (index >= 0) state.items[index] = updated;
}

async function decide(decision) {
  if (state.decisionInFlight) return;
  const item = currentItem();
  if (!item) return;
  if (decision === "organize" && !state.selectedDestination) {
    toast("Primero elegí o creá la carpeta a la que querés mover la foto.", 5200);
    $("newFolderName").focus();
    return;
  }
  if (decision === "print" && item.type !== "IMAGE") {
    toast("La opción A imprimir está disponible solamente para imágenes.", 5200);
    return;
  }
  state.decisionInFlight = true;
  const previous = item.decision;
  clearMedia();
  card.classList.add("loading");
  try {
    const result = await api(`/api/local/media/${encodeURIComponent(item.item_id)}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        destinationRelativePath: decision === "organize" ? state.selectedDestination : null,
      }),
    });
    state.history.push({ id: item.item_id, previous });
    replaceItem(result.item);
    state.folder = result.status;
    state.renderedItemId = null;
    render();
    if (decision === "delete") toast(`Movido a ${state.folder.discardPath}`);
    if (decision === "print") toast("Conservada y copiada a “A imprimir”.");
    if (decision === "organize") {
      const selected = state.destinationFolders.find(
        (folder) => folder.relativePath === state.selectedDestination,
      );
      toast(`Movido a “${selected?.name || state.selectedDestination}”.`);
    }
  } catch (error) {
    state.renderedItemId = null;
    render();
    toast(error.message, 5200);
  } finally {
    state.decisionInFlight = false;
    render();
  }
}

async function undo() {
  if (state.decisionInFlight) return;
  const entry = state.history.pop();
  if (!entry) return;
  state.decisionInFlight = true;
  try {
    const result = await api(`/api/local/media/${encodeURIComponent(entry.id)}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision: entry.previous }),
    });
    replaceItem(result.item);
    state.folder = result.status;
    state.renderedItemId = null;
    render();
    toast("Última decisión deshecha.");
  } catch (error) {
    state.history.push(entry);
    toast(error.message, 5200);
  } finally {
    state.decisionInFlight = false;
    render();
  }
}

function installDrag() {
  card.addEventListener("pointerdown", (event) => {
    if (event.target.closest("video, audio, button, input")) return;
    state.dragStartX = event.clientX;
    card.setPointerCapture(event.pointerId);
  });
  card.addEventListener("pointermove", (event) => {
    if (state.dragStartX === null) return;
    const dx = event.clientX - state.dragStartX;
    card.style.transition = "none";
    card.style.transform = `translateX(${dx}px) rotate(${dx / 24}deg)`;
    card.querySelector(".keep-hint").style.opacity = Math.max(0, dx / 110);
    card.querySelector(".delete-hint").style.opacity = Math.max(0, -dx / 110);
  });
  card.addEventListener("pointerup", (event) => {
    if (state.dragStartX === null) return;
    const dx = event.clientX - state.dragStartX;
    state.dragStartX = null;
    card.style.transition = "";
    card.style.transform = "";
    card.querySelector(".keep-hint").style.opacity = 0;
    card.querySelector(".delete-hint").style.opacity = 0;
    if (dx > 100) decide("keep");
    else if (dx < -100) decide("delete");
  });
}

function installKeyboard() {
  document.addEventListener("keydown", (event) => {
    if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target instanceof Element
      && event.target.closest("input, textarea, select, video, audio, [contenteditable='true']")) return;
    const actions = {
      ArrowLeft: () => decide("delete"),
      ArrowRight: () => decide("keep"),
      ArrowUp: () => decide("organize"),
      ArrowDown: undo,
      i: () => decide("print"),
    };
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    const action = actions[key];
    if (!action) return;
    event.preventDefault();
    action();
  });
}

async function loadExtensionStatus() {
  const status = await api("/api/status");
  state.extensionPath = status.extensionPath || "";
  $("extensionPath").textContent = state.extensionPath || "Carpeta no disponible";
  const badge = $("extensionBadge");
  badge.textContent = status.extensionActive
    ? `Extensión activa${status.extensionVersion ? ` · v${status.extensionVersion}` : ""}`
    : "Extensión sin detectar · abrí Google Photos";
  badge.classList.toggle("active", Boolean(status.extensionActive));
  badge.classList.toggle("inactive", !status.extensionActive);
}

async function loadExtensionQueue() {
  const payload = await api("/api/extension/decisions");
  const root = $("extensionQueue");
  root.replaceChildren();
  if (!payload.items.length) {
    root.textContent = "Todavía no hay operaciones registradas.";
    return;
  }
  for (const item of payload.items.slice(0, 8)) {
    const row = document.createElement("div");
    row.className = `queue-item ${item.album_status}`;
    const icon = item.album_status === "added"
      ? "✓"
      : item.album_status === "trashed"
        ? "🗑"
        : ["restored", "undone"].includes(item.album_status)
          ? "↶"
          : "!";
    row.textContent = `${icon} ${item.photo_id.slice(0, 18)} · ${item.message || item.album_status}`;
    root.appendChild(row);
  }
}

$("selectFolderButton").addEventListener("click", chooseLocalFolder);
$("rescanFolderButton").addEventListener("click", rescanLocalFolder);
$("deleteButton").addEventListener("click", () => decide("delete"));
$("organizeButton").addEventListener("click", () => decide("organize"));
$("keepButton").addEventListener("click", () => decide("keep"));
$("printButton").addEventListener("click", () => decide("print"));
$("undoButton").addEventListener("click", undo);
$("createDestinationFolderButton").addEventListener("click", createDestinationFolder);
$("newFolderName").addEventListener("keydown", (event) => {
  if (event.key === "Enter") createDestinationFolder();
});
$("destinationFolderSelect").addEventListener("change", (event) => {
  selectDestinationFolder(event.target.value);
});
$("copyExtensionPath").addEventListener("click", async () => {
  if (!state.extensionPath) return;
  try {
    await navigator.clipboard.writeText(state.extensionPath);
    toast("Carpeta de la extensión copiada.");
  } catch {
    const range = document.createRange();
    range.selectNodeContents($("extensionPath"));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    toast("La carpeta quedó seleccionada. Presioná Ctrl+C.");
  }
});

installDrag();
installKeyboard();
Promise.all([loadLocalLibrary(), loadExtensionStatus(), loadExtensionQueue()])
  .catch((error) => toast(error.message, 5200));
window.setInterval(() => loadExtensionStatus().catch(() => {}), 30000);
