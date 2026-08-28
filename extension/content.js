(() => {
  const ALBUM_NAME = "Fotos a eliminar";
  const PHOTO_PATH = /^\/photo\/([^/?#]+)/;
  const labels = {
    more: ["More options", "Más opciones"],
    addToAlbum: ["Add to album", "Agregar al álbum", "Añadir al álbum"],
    moveToTrash: ["Move to trash", "Move to bin", "Mover a la papelera"],
    movedToTrash: ["Moved to trash", "Moved to bin", "Movido a la papelera", "Se movió a la papelera"],
    close: ["Close", "Cerrar"],
  };

  let busy = false;
  let discardMode = "album";
  let gestureStart = null;
  let lastUrl = location.href;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function photoId() {
    return location.pathname.match(PHOTO_PATH)?.[1] || null;
  }

  function normalized(value) {
    return (value || "").trim().toLocaleLowerCase();
  }

  function byAccessibleName(role, candidates) {
    const expected = candidates.map(normalized);
    return [...document.querySelectorAll(`[role="${role}"], ${role === "button" ? "button" : "span"}`)]
      .find((element) => {
        const name = element.getAttribute("aria-label") || element.textContent;
        return expected.includes(normalized(name));
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
      showToast(`Agregada a “${ALBUM_NAME}”. Todavía no fue eliminada.`);
      await goNext();
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

      await waitFor(() => {
        if (photoId() !== media.id) return true;
        return [...document.querySelectorAll('[role="status"], [role="alert"]')]
          .some((element) => labels.movedToTrash.some((label) => normalized(element.textContent).includes(normalized(label))));
      }, 7000);

      await record("delete", "trashed", "Movida a la Papelera", media);
      showToast("Movida a la Papelera de Google Photos.");
      if (photoId() === media.id) await goNext();
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

  async function keepCurrentPhoto() {
    if (busy || !photoId()) return;
    setBusy(true);
    await record("keep", "not_needed", "Conservar");
    showToast("Marcada para conservar.");
    await goNext();
    setBusy(false);
  }

  async function goNext() {
    const next = [...document.querySelectorAll("button")].find((button) => {
      const name = normalized(button.getAttribute("aria-label"));
      return name === "view next photo" || name === "ver siguiente foto";
    });
    next?.click();
    await sleep(250);
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
          <option value="trash">Papelera</option>
        </select>
      </label>
      <button id="swipeclean-delete" type="button">← Álbum</button>
      <button id="swipeclean-prepare" type="button">Preparar álbum</button>
      <button id="swipeclean-keep" type="button">Conservar →</button>
    `;
    const mode = controls.querySelector("#swipeclean-mode");
    const discard = controls.querySelector("#swipeclean-delete");
    const prepare = controls.querySelector("#swipeclean-prepare");
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
    controls.querySelector("#swipeclean-keep").addEventListener("click", keepCurrentPhoto);
    document.body.appendChild(controls);
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
    else keepCurrentPhoto();
  }, true);

  function handleKeyboardDecision(event) {
    if (!photoId() || busy || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target instanceof Element
      && event.target.closest("input, textarea, select, video, [contenteditable='true']")) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    if (event.key === "ArrowLeft") discardCurrentPhoto();
    else keepCurrentPhoto();
  }

  window.addEventListener("keydown", handleKeyboardDecision, true);

  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) lastUrl = location.href;
    mountControls();
  });
  function beginWatchingPhotos() {
    if (!document.documentElement) {
      window.setTimeout(beginWatchingPhotos, 25);
      return;
    }
    observer.observe(document.documentElement, { childList: true, subtree: true });
    mountControls();
  }

  beginWatchingPhotos();
  heartbeat();
  window.setInterval(heartbeat, 30000);
})();
