(() => {
  const ALBUM_NAME = "Fotos a eliminar";
  const PHOTO_PATH = /(?:^|\/)photo\/([^/?#]+)/;
  const RESUME_STORAGE_KEY = "photoSwipperResumePoint";
  const labels = {
    more: ["More options", "Más opciones"],
    addToAlbum: ["Add to album", "Agregar al álbum", "Añadir al álbum"],
    moveToTrash: ["Move to trash", "Move to bin", "Mover a la papelera"],
    movedToTrash: ["Moved to trash", "Moved to bin", "Movido a la papelera", "Se movió a la papelera"],
    undo: ["Undo", "Deshacer"],
    restored: [
      "Restored", "Item restored", "Photo restored",
      "Restaurado", "Restaurada", "Elemento restaurado", "Foto restaurada",
      "Se restauró", "Se ha restaurado", "Se restableció",
    ],
    close: ["Close", "Cerrar"],
    next: [
      "View next photo", "Next photo", "Next image", "Next item",
      "Ver siguiente foto", "Siguiente foto", "Foto siguiente",
      "Siguiente imagen", "Elemento siguiente",
    ],
  };

  let busy = false;
  let discardMode = "trash";
  let gestureStart = null;
  let lastUrl = location.href;
  let rightKeyHeld = false;
  let rapidKeepLoopActive = false;
  let rapidReachedEnd = false;
  let queuedKeepCount = 0;
  let lastSavedPhotoId = null;
  let suppressedCheckpointId = null;
  let resumeAttempted = false;
  let resumeStorageQueue = Promise.resolve();
  const actionHistory = [];
  const MAX_ACTION_HISTORY = 30;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function photoIdFromPath(pathname) {
    return pathname.match(PHOTO_PATH)?.[1] || null;
  }

  function photoId() {
    return photoIdFromPath(location.pathname);
  }

  function storageGetResumePoint() {
    return new Promise((resolve) => {
      chrome.storage.local.get(RESUME_STORAGE_KEY, (result) => {
        if (chrome.runtime.lastError) {
          resolve(null);
          return;
        }
        resolve(result?.[RESUME_STORAGE_KEY] || null);
      });
    });
  }

  function storageSetResumePoint(point) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [RESUME_STORAGE_KEY]: point }, () => {
        void chrome.runtime.lastError;
        resolve();
      });
    });
  }

  function storageRemoveResumePoint() {
    return new Promise((resolve) => {
      chrome.storage.local.remove(RESUME_STORAGE_KEY, () => {
        void chrome.runtime.lastError;
        resolve();
      });
    });
  }

  function enqueueResumeStorage(operation) {
    resumeStorageQueue = resumeStorageQueue.then(operation, operation);
    return resumeStorageQueue;
  }

  function validResumePoint(value) {
    if (!value || typeof value.id !== "string" || typeof value.url !== "string") return null;
    try {
      const url = new URL(value.url);
      const id = photoIdFromPath(url.pathname);
      if (url.origin !== location.origin || !id || id !== value.id) return null;
      return { id, url: url.href, updatedAt: value.updatedAt || null };
    } catch {
      return null;
    }
  }

  function isLibraryEntryPath() {
    const path = location.pathname.replace(/^\/u\/\d+(?=\/|$)/, "");
    return path === "" || path === "/";
  }

  function rememberCurrentPhoto() {
    const id = photoId();
    if (!id || id === lastSavedPhotoId || id === suppressedCheckpointId) return;
    suppressedCheckpointId = null;
    lastSavedPhotoId = id;
    const point = { id, url: location.href, updatedAt: Date.now() };
    void enqueueResumeStorage(() => storageSetResumePoint(point));
  }

  function markPhotoProcessed(id) {
    if (!id) return Promise.resolve();
    suppressedCheckpointId = id;
    if (lastSavedPhotoId === id) lastSavedPhotoId = null;
    return enqueueResumeStorage(async () => {
      const current = validResumePoint(await storageGetResumePoint());
      if (current?.id === id) await storageRemoveResumePoint();
    });
  }

  async function maybeResumeLastPhoto() {
    if (resumeAttempted) return;
    resumeAttempted = true;
    if (photoId()) {
      rememberCurrentPhoto();
      return;
    }
    if (!isLibraryEntryPath()) return;

    const stored = await enqueueResumeStorage(() => storageGetResumePoint());
    const point = validResumePoint(stored);
    if (!point) {
      if (stored) await enqueueResumeStorage(() => storageRemoveResumePoint());
      return;
    }
    lastSavedPhotoId = point.id;
    location.replace(point.url);
  }

  function normalized(value) {
    return (value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLocaleLowerCase();
  }

  function accessibleName(element) {
    return element.getAttribute("aria-label")
      || element.getAttribute("data-tooltip")
      || element.getAttribute("title")
      || element.textContent
      || "";
  }

  function byAccessibleName(role, candidates) {
    const expected = candidates.map(normalized);
    return [...document.querySelectorAll(`[role="${role}"], ${role === "button" ? "button" : "span"}`)]
      .find((element) => {
        const name = accessibleName(element);
        return expected.includes(normalized(name));
      });
  }

  function statusWithText(candidates) {
    const expected = candidates.map(normalized);
    return [...document.querySelectorAll('[role="status"], [role="alert"]')]
      .reverse()
      .find((element) => expected.some((label) => normalized(element.textContent).includes(label)));
  }

  function visibleTrashUndoButton() {
    const status = statusWithText(labels.movedToTrash);
    if (!status) return null;
    return [...status.querySelectorAll('button, [role="button"]')]
      .find((button) => labels.undo.some((label) => {
        const name = accessibleName(button);
        return normalized(name) === normalized(label) || normalized(name).includes(normalized(label));
      })) || null;
  }

  function findOlderNavigationButton() {
    const expected = labels.next.map(normalized);
    const candidates = [...document.querySelectorAll('button, [role="button"]')]
      .filter((element) => !element.closest("#swipeclean-controls") && !element.disabled);

    const labeled = candidates.find((element) => {
      const name = normalized(accessibleName(element));
      return expected.some((label) => name === label || name.includes(label));
    });
    if (labeled) return labeled;

    const iconNames = new Set(["chevron_right", "navigate_next", "arrow_forward_ios", "›", ">"]);
    return candidates.find((element) => {
      const rect = element.getBoundingClientRect();
      const icon = normalized(element.textContent);
      return iconNames.has(icon)
        && rect.width > 0
        && rect.height > 0
        && rect.left > window.innerWidth / 2
        && rect.top > window.innerHeight * 0.2
        && rect.bottom < window.innerHeight * 0.8;
    });
  }

  async function waitFor(find, timeout = 5000) {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      const result = find();
      if (result) return result;
      await sleep(100);
    }
    throw new Error("Google Photos no mostró el control esperado.");
  }

  function showToast(message, kind = "info") {
    document.getElementById("swipeclean-toast")?.remove();
    const toast = document.createElement("div");
    toast.id = "swipeclean-toast";
    toast.dataset.kind = kind;
    toast.textContent = message;
    document.body.appendChild(toast);
    window.setTimeout(() => toast.remove(), 5200);
  }

  function setBusy(value) {
    busy = value;
    document.querySelectorAll("#swipeclean-controls button, #swipeclean-controls select").forEach((control) => {
      control.disabled = value;
    });
    updateUndoControl();
    if (!value) window.queueMicrotask(flushQueuedKeep);
  }

  function updateUndoControl() {
    const undo = document.getElementById("swipeclean-undo");
    if (!undo) return;
    undo.disabled = busy || actionHistory.length === 0;
    const latest = actionHistory.at(-1);
    undo.title = latest?.kind === "trash"
      ? "Restaurar la última foto mientras Google muestre Deshacer"
      : latest?.kind === "keep"
        ? "Volver a la última foto conservada"
        : "La última acción no se puede deshacer automáticamente";
  }

  function rememberAction(action) {
    actionHistory.push(action);
    if (actionHistory.length > MAX_ACTION_HISTORY) actionHistory.shift();
    updateUndoControl();
  }

  function sendToSwipeClean(type, payload = null) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type, payload }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (!response?.ok) {
          reject(new Error(response?.error || "El asistente local no respondió."));
          return;
        }
        resolve(response.data);
      });
    });
  }

  async function record(decision, albumStatus, message, media = null) {
    const id = media?.id || photoId();
    if (!id) return;
    try {
      await sendToSwipeClean("swipeclean:record", {
        photoId: id,
        photoUrl: media?.url || location.href,
        decision,
        albumStatus,
        message,
      });
    } catch {
      showToast("La decisión se aplicó en Google Photos, pero la app local no está abierta.", "error");
    }
  }

  async function heartbeat() {
    try {
      await sendToSwipeClean("swipeclean:heartbeat");
    } catch {
      // La interfaz de Google Photos sigue funcionando aunque la app local esté cerrada.
    }
  }

  async function openAlbumPicker() {
    const more = await waitFor(() => byAccessibleName("button", labels.more));
    more.click();
    const add = await waitFor(() => {
      const candidates = [...document.querySelectorAll('[role="menuitem"]')];
      return candidates.find((element) => labels.addToAlbum.some((label) => normalized(element.textContent).includes(normalized(label))));
    });
    add.click();
    return waitFor(() => document.querySelector('[role="dialog"]'));
  }

  async function filterAlbum(dialog) {
    const search = await waitFor(() => dialog.querySelector('input[type="text"], input:not([type])'));
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(search, ALBUM_NAME);
    search.dispatchEvent(new Event("input", { bubbles: true }));
    search.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(700);
    return [...dialog.querySelectorAll('[role="option"]')]
      .find((option) => normalized(option.textContent).startsWith(normalized(ALBUM_NAME)));
  }

  async function addCurrentPhotoToAlbum() {
    if (busy || !photoId()) return;
    const media = { id: photoId(), url: location.href };
    setBusy(true);
    try {
      const dialog = await openAlbumPicker();
      const album = await filterAlbum(dialog);
      if (!album) {
        byAccessibleName("button", labels.close)?.click();
        const message = `Primero creá manualmente el álbum “${ALBUM_NAME}” en Google Photos.`;
        await record("delete", "failed", message, media);
        showToast(message, "error");
        return;
      }
      album.click();
      await waitFor(() => !document.querySelector('[role="dialog"]'), 5000);
      await record("delete", "added", `Agregada a ${ALBUM_NAME}`, media);
      await markPhotoProcessed(media.id);
      const advanced = await goToOlderPhoto(media.id);
      rememberAction({ kind: "album", media });
      showToast(advanced
        ? `Agregada a “${ALBUM_NAME}”. Mostrando la siguiente foto, normalmente más antigua.`
        : `Agregada a “${ALBUM_NAME}”, pero no encontré la siguiente foto.`);
    } catch (error) {
      await record("delete", "failed", error.message, media);
      showToast(`No se pudo agregar al álbum: ${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function moveCurrentPhotoToTrash() {
    if (busy || !photoId()) return;
    const media = { id: photoId(), url: location.href };
    setBusy(true);
    try {
      const trash = await waitFor(() => byAccessibleName("button", labels.moveToTrash));
      trash.click();

      const dialog = await waitFor(
        () => document.querySelector('[role="dialog"]'),
        1200,
      ).catch(() => null);
      if (dialog) {
        const confirmation = [...dialog.querySelectorAll('button, [role="button"]')]
          .find((button) => labels.moveToTrash.some((label) => {
            const name = button.getAttribute("aria-label") || button.textContent;
            return normalized(name).includes(normalized(label));
          }));
        if (!confirmation) throw new Error("Google Photos no mostró la confirmación de Papelera.");
        confirmation.click();
      }

      await waitFor(() => statusWithText(labels.movedToTrash), 7000);

      await markPhotoProcessed(media.id);
      rememberAction({ kind: "trash", media });
      void record("delete", "trashed", "Movida a la Papelera", media);
      showToast("Movida a la Papelera de Google Photos.");
      if (photoId() === media.id) await goToOlderPhoto(media.id);
    } catch (error) {
      await record("delete", "failed", error.message, media);
      showToast(`No se pudo mover a la Papelera: ${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  function discardCurrentPhoto() {
    if (discardMode === "trash") moveCurrentPhotoToTrash();
    else addCurrentPhotoToAlbum();
  }

  function requestKeepCurrentPhoto() {
    if (!photoId()) return;
    if (busy) {
      // Conserva pulsaciones cortas realizadas mientras Google termina de
      // cambiar de foto, en vez de perderlas silenciosamente.
      queuedKeepCount = Math.min(queuedKeepCount + 1, 6);
      return;
    }
    void keepCurrentPhoto();
  }

  function flushQueuedKeep() {
    if (busy || queuedKeepCount === 0 || rapidKeepLoopActive) return;
    queuedKeepCount -= 1;
    void keepCurrentPhoto();
  }

  async function keepCurrentPhoto({ quiet = false } = {}) {
    if (busy || !photoId()) return false;
    setBusy(true);
    const media = { id: photoId(), url: location.href };
    try {
      await record("keep", "not_needed", "Conservar");
      await markPhotoProcessed(media.id);
      const advanced = await goToOlderPhoto(media.id);
      if (advanced) rememberAction({
        kind: "keep",
        media,
      });
      if (!quiet) {
        showToast(advanced
          ? "Marcada para conservar. Mostrando la siguiente foto, normalmente más antigua."
          : "Marcada para conservar, pero no encontré la siguiente foto.");
      }
      return advanced;
    } finally {
      setBusy(false);
    }
  }

  async function undoLastAction() {
    if (busy) return;
    const latest = actionHistory.at(-1);
    if (!latest) {
      showToast("Todavía no hay una acción para deshacer.");
      return;
    }
    if (latest.kind === "album") {
      showToast(
        `Google Photos no ofrece un Deshacer seguro para quitar la foto de “${ALBUM_NAME}”.`,
        "error",
      );
      return;
    }

    setBusy(true);
    try {
      if (latest.kind === "keep") {
        actionHistory.pop();
        await record("pending", "undone", "Conservar deshecho", latest.media);
        location.assign(latest.media.url);
        return;
      }

      const undo = visibleTrashUndoButton();
      if (!undo) {
        showToast(
          "Google Photos ya ocultó Deshacer. La foto sigue en Papelera y podés restaurarla manualmente.",
          "error",
        );
        return;
      }

      actionHistory.pop();
      undo.click();
      const confirmed = await waitFor(
        () => statusWithText(labels.restored) || (photoId() === latest.media.id ? latest.media.id : null),
        4500,
      )
        .catch(() => null);
      if (!confirmed) {
        await record(
          "delete",
          "failed",
          "Google recibió Deshacer, pero no mostró una confirmación de restauración.",
          latest.media,
        );
        showToast(
          "Se pulsó Deshacer, pero Google Photos no confirmó la restauración. Revisá Papelera.",
          "error",
        );
        return;
      }

      await record("pending", "restored", "Restaurada desde Papelera", latest.media);
      showToast("Última foto restaurada. Volviendo a ella.");
      if (photoId() !== latest.media.id) {
        window.setTimeout(() => location.assign(latest.media.url), 350);
      }
    } finally {
      setBusy(false);
    }
  }

  async function goToOlderPhoto(startingId = photoId()) {
    // En la biblioteca principal, Google Photos ordena de reciente a antigua,
    // por lo que "siguiente" normalmente avanza hacia atrás en el tiempo. En
    // álbumes o búsquedas se respeta el orden definido por ese contexto.
    // Durante una navegación rápida Google reconstruye los controles. Esperar
    // a que reaparezcan evita que una pulsación corta se pierda en esa ventana.
    const next = await waitFor(findOlderNavigationButton, 1800).catch(() => null);
    if (!next) return false;
    next.click();
    try {
      await waitFor(() => {
        const currentId = photoId();
        return currentId && currentId !== startingId ? currentId : null;
      }, 3500);
      rememberCurrentPhoto();
      return true;
    } catch {
      return false;
    }
  }

  async function runRapidKeepLoop() {
    if (rapidKeepLoopActive || rapidReachedEnd) return;
    rapidKeepLoopActive = true;
    let keptCount = 0;
    try {
      while (rightKeyHeld) {
        if (busy) {
          await sleep(30);
          continue;
        }
        if (!photoId()) break;
        const advanced = await keepCurrentPhoto({ quiet: true });
        keptCount += 1;
        if (!advanced) {
          rapidReachedEnd = true;
          break;
        }
        await sleep(35);
      }
    } finally {
      rapidKeepLoopActive = false;
      if (keptCount > 0) {
        showToast(`${keptCount} foto${keptCount === 1 ? "" : "s"} conservada${keptCount === 1 ? "" : "s"} con avance rápido.`);
      }
      window.queueMicrotask(flushQueuedKeep);
    }
  }

  async function prepareAlbum() {
    if (busy || !photoId()) return;
    setBusy(true);
    try {
      const dialog = await openAlbumPicker();
      const album = await filterAlbum(dialog);
      if (album) {
        byAccessibleName("button", labels.close)?.click();
        showToast(`El álbum “${ALBUM_NAME}” ya está disponible.`);
      } else {
        showToast(`Elegí “Nuevo álbum”, creá “${ALBUM_NAME}” y luego cerrá el selector.`);
      }
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function mountControls() {
    const visible = Boolean(photoId());
    let controls = document.getElementById("swipeclean-controls");
    if (!visible) {
      controls?.remove();
      return;
    }
    if (controls) return;
    if (!document.body) return;
    controls = document.createElement("div");
    controls.id = "swipeclean-controls";
    controls.innerHTML = `
      <label class="swipeclean-mode-label">
        Destino
        <select id="swipeclean-mode" aria-label="Destino del descarte">
          <option value="album">Álbum</option>
          <option value="trash" selected>Papelera</option>
        </select>
      </label>
      <button id="swipeclean-delete" type="button">← Papelera</button>
      <button id="swipeclean-prepare" type="button">Preparar álbum</button>
      <button id="swipeclean-keep" type="button" title="Conservar y avanzar a la siguiente foto, normalmente más antigua">Conservar →</button>
      <button id="swipeclean-undo" type="button" disabled>↓ Deshacer</button>
    `;
    const mode = controls.querySelector("#swipeclean-mode");
    const discard = controls.querySelector("#swipeclean-delete");
    const prepare = controls.querySelector("#swipeclean-prepare");
    mode.value = discardMode;
    controls.dataset.mode = discardMode;
    discard.textContent = discardMode === "trash" ? "← Papelera" : "← Álbum";
    prepare.hidden = discardMode === "trash";
    mode.addEventListener("change", () => {
      if (mode.value === "trash") {
        const accepted = window.confirm(
          "Activar Papelera: cada swipe o flecha izquierda moverá inmediatamente el elemento a la Papelera de Google Photos. ¿Continuar?",
        );
        if (!accepted) {
          mode.value = "album";
          return;
        }
      }
      discardMode = mode.value;
      controls.dataset.mode = discardMode;
      discard.textContent = discardMode === "trash" ? "← Papelera" : "← Álbum";
      prepare.hidden = discardMode === "trash";
      showToast(discardMode === "trash" ? "Modo Papelera activo." : `Modo álbum “${ALBUM_NAME}” activo.`);
    });
    discard.addEventListener("click", discardCurrentPhoto);
    controls.querySelector("#swipeclean-prepare").addEventListener("click", prepareAlbum);
    controls.querySelector("#swipeclean-keep").addEventListener("click", requestKeepCurrentPhoto);
    controls.querySelector("#swipeclean-undo").addEventListener("click", undoLastAction);
    document.body.appendChild(controls);
    updateUndoControl();
  }

  document.addEventListener("pointerdown", (event) => {
    if (!photoId() || event.target.closest("#swipeclean-controls")) return;
    gestureStart = { x: event.clientX, y: event.clientY };
  }, true);

  document.addEventListener("pointerup", (event) => {
    if (!gestureStart || busy) return;
    const dx = event.clientX - gestureStart.x;
    const dy = event.clientY - gestureStart.y;
    gestureStart = null;
    if (Math.abs(dx) < 140 || Math.abs(dx) < Math.abs(dy) * 1.4) return;
    if (dx < 0) discardCurrentPhoto();
    else requestKeepCurrentPhoto();
  }, true);

  function handleKeyboardDecision(event) {
    if (!photoId() || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target instanceof Element
      && event.target.closest("input, textarea, select, video, [contenteditable='true']")) return;
    if (!["ArrowLeft", "ArrowRight", "ArrowDown"].includes(event.key)) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    if (event.key === "ArrowDown") {
      if (!event.repeat) void undoLastAction();
      return;
    }
    if (event.key === "ArrowLeft") {
      // No repetir automáticamente una operación que puede terminar en álbum o
      // Papelera. La repetición rápida está reservada para conservar.
      if (!busy && !event.repeat) discardCurrentPhoto();
      return;
    }

    rightKeyHeld = true;
    if (event.repeat) {
      void runRapidKeepLoop();
    } else {
      rapidReachedEnd = false;
      requestKeepCurrentPhoto();
    }
  }

  function handleKeyboardRelease(event) {
    if (event.key !== "ArrowRight") return;
    rightKeyHeld = false;
    rapidReachedEnd = false;
  }

  window.addEventListener("keydown", handleKeyboardDecision, true);
  window.addEventListener("keyup", handleKeyboardRelease, true);

  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      rememberCurrentPhoto();
    }
    mountControls();
  });
  function beginWatchingPhotos() {
    if (!document.documentElement) {
      window.setTimeout(beginWatchingPhotos, 25);
      return;
    }
    observer.observe(document.documentElement, { childList: true, subtree: true });
    mountControls();
    void maybeResumeLastPhoto();
  }

  beginWatchingPhotos();
  heartbeat();
  window.setInterval(heartbeat, 30000);
})();
