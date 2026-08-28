import hashlib
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any

from src.mvp_store import MvpStore


IMAGE_EXTENSIONS = {
    ".avif", ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg",
    ".png", ".tif", ".tiff", ".webp",
}
VIDEO_EXTENSIONS = {
    ".3gp", ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg",
    ".mpg", ".webm", ".wmv",
}
AUDIO_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus",
    ".wav", ".wma",
}
DISCARD_FOLDER_NAME = "_Photo_Swipper_Filter_Para_Eliminar"
LEGACY_DISCARD_FOLDER_NAMES = {"_SwipeClean_Para_Eliminar"}

MIME_OVERRIDES = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".m4a": "audio/mp4",
    ".mkv": "video/x-matroska",
    ".opus": "audio/ogg",
}


def choose_folder() -> str | None:
    """Abre el selector nativo de Windows sin exponer rutas al navegador."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        selected = filedialog.askdirectory(
            parent=root,
            title="Elegí la carpeta de fotos, videos y audios",
            mustexist=True,
        )
        return selected or None
    finally:
        root.destroy()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _media_type(extension: str) -> str | None:
    if extension in IMAGE_EXTENSIONS:
        return "IMAGE"
    if extension in VIDEO_EXTENSIONS:
        return "VIDEO"
    if extension in AUDIO_EXTENSIONS:
        return "AUDIO"
    return None


def _mime_type(path: Path, media_type: str) -> str:
    guessed = MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    defaults = {"IMAGE": "image/jpeg", "VIDEO": "video/mp4", "AUDIO": "audio/mpeg"}
    return guessed or defaults[media_type]


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


class LocalMediaLibrary:
    def __init__(self, store: MvpStore):
        self.store = store

    def scan(self, selected_path: str | Path) -> dict[str, Any]:
        root = Path(selected_path).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("La carpeta elegida no es válida.")
        discard = (root / DISCARD_FOLDER_NAME).resolve()
        excluded_discards = {
            discard,
            *((root / name).resolve() for name in LEGACY_DISCARD_FOLDER_NAMES),
        }
        items: list[dict[str, Any]] = []

        for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current).resolve()
            directories[:] = [
                name
                for name in directories
                if (current_path / name).resolve() not in excluded_discards
            ]
            for filename in filenames:
                path = (current_path / filename).resolve()
                if not _is_within(path, root) or any(
                    _is_within(path, excluded) for excluded in excluded_discards
                ):
                    continue
                kind = _media_type(path.suffix.lower())
                if not kind:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                relative = path.relative_to(root)
                stable_key = f"{str(root).casefold()}\0{relative.as_posix().casefold()}"
                items.append(
                    {
                        "item_id": hashlib.sha256(stable_key.encode("utf-8")).hexdigest(),
                        "original_relative_path": relative.as_posix(),
                        "current_path": str(path),
                        "type": kind,
                        "filename": path.name,
                        "mime_type": _mime_type(path, kind),
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                    }
                )

        self.store.sync_local_library(str(root), str(discard), items)
        return self.status()

    def status(self) -> dict[str, Any]:
        library = self.store.get_local_library()
        items = self.store.list_local_media() if library else []
        counts = {"pending": 0, "keep": 0, "delete": 0, "later": 0}
        for item in items:
            counts[item["decision"]] = counts.get(item["decision"], 0) + 1
        return {
            "selected": bool(library),
            "rootPath": library["root_path"] if library else None,
            "discardPath": library["discard_path"] if library else None,
            "counts": counts,
            "total": len(items),
        }

    def list_items(self) -> list[dict[str, Any]]:
        return self.store.list_local_media()

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        return self.store.get_local_media(item_id)

    def content_path(self, item_id: str) -> Path:
        item = self.get_item(item_id)
        library = self.store.get_local_library()
        if not item or not library:
            raise FileNotFoundError("Archivo no encontrado.")
        root = Path(library["root_path"]).resolve()
        path = Path(item["current_path"]).resolve(strict=True)
        if not path.is_file() or not _is_within(path, root):
            raise FileNotFoundError("El archivo ya no está dentro de la biblioteca elegida.")
        return path

    def decide(self, item_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"pending", "keep", "delete", "later"}:
            raise ValueError("Decisión inválida.")
        item = self.get_item(item_id)
        library = self.store.get_local_library()
        if not item or not library:
            raise FileNotFoundError("Archivo no encontrado.")

        root = Path(library["root_path"]).resolve()
        discard = Path(library["discard_path"]).resolve()
        source = Path(item["current_path"]).resolve(strict=True)
        if not source.is_file() or not _is_within(source, root):
            raise FileNotFoundError("El archivo ya no está disponible.")

        current_decision = item["decision"]
        new_path = source
        new_relative: str | None = None

        if decision == "delete" and current_decision != "delete":
            relative = Path(item["original_relative_path"])
            destination = (discard / relative).resolve()
            if not _is_within(destination, discard):
                raise ValueError("La ruta de destino no es segura.")
            destination = _unique_destination(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            new_path = Path(shutil.move(str(source), str(destination))).resolve()
        elif decision != "delete" and current_decision == "delete":
            destination = (root / Path(item["original_relative_path"])).resolve()
            if not _is_within(destination, root) or _is_within(destination, discard):
                raise ValueError("La ruta de restauración no es segura.")
            destination = _unique_destination(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            new_path = Path(shutil.move(str(source), str(destination))).resolve()
            new_relative = new_path.relative_to(root).as_posix()

        self.store.update_local_media(
            item_id,
            decision,
            current_path=str(new_path),
            original_relative_path=new_relative,
        )
        return self.get_item(item_id) or {}
