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
PRINT_FOLDER_NAME = "A imprimir"
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
INVALID_FOLDER_CHARACTERS = set('<>:"/\\|?*')

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
        excluded_organize_folders = {
            (root / folder["relative_path"]).resolve()
            for folder in self.store.list_local_organize_folders(str(root))
        }
        excluded_folders = excluded_discards | excluded_organize_folders | {
            (root / PRINT_FOLDER_NAME).resolve()
        }
        items: list[dict[str, Any]] = []

        for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current).resolve()
            directories[:] = [
                name
                for name in directories
                if not any(
                    _is_within((current_path / name).resolve(), excluded)
                    for excluded in excluded_folders
                )
            ]
            for filename in filenames:
                path = (current_path / filename).resolve()
                if not _is_within(path, root) or any(
                    _is_within(path, excluded) for excluded in excluded_folders
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
        counts = {"pending": 0, "keep": 0, "delete": 0, "organize": 0}
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

    def organize_folders(self) -> dict[str, Any]:
        library = self.store.get_local_library()
        if not library:
            return {"folders": [], "selected": None}
        root = Path(library["root_path"]).resolve()
        discard = Path(library["discard_path"]).resolve()
        folders = []
        selected = None
        for stored in self.store.list_local_organize_folders(str(root)):
            path = (root / stored["relative_path"]).resolve()
            if (
                not _is_within(path, root)
                or _is_within(path, discard)
                or not path.is_dir()
            ):
                continue
            entry = {
                "name": stored["name"],
                "relativePath": path.relative_to(root).as_posix(),
            }
            folders.append(entry)
            if stored["selected"]:
                selected = entry["relativePath"]
        return {"folders": folders, "selected": selected}

    def create_organize_folder(self, name: str) -> dict[str, Any]:
        library = self.store.get_local_library()
        if not library:
            raise ValueError("Primero elegí la carpeta principal.")
        clean_name = self._validate_folder_name(name)
        root = Path(library["root_path"]).resolve()
        discard = Path(library["discard_path"]).resolve()
        destination = (root / clean_name).resolve()
        if not _is_within(destination, root) or _is_within(destination, discard):
            raise ValueError("La carpeta de destino no es segura.")
        relative = destination.relative_to(root).as_posix()
        registered = {
            folder["relative_path"].casefold()
            for folder in self.store.list_local_organize_folders(str(root))
        }
        if destination.exists() and not destination.is_dir():
            raise ValueError("Ya existe un archivo con ese nombre.")
        if destination.exists() and relative.casefold() not in registered:
            raise ValueError("Ya existe una carpeta con ese nombre. Escribí un nombre nuevo.")
        destination.mkdir(parents=False, exist_ok=True)
        self.store.save_local_organize_folder(str(root), relative, destination.name)
        return self.organize_folders()

    def select_organize_folder(self, relative_path: str) -> dict[str, Any]:
        library = self.store.get_local_library()
        if not library:
            raise ValueError("Primero elegí la carpeta principal.")
        root = Path(library["root_path"]).resolve()
        discard = Path(library["discard_path"]).resolve()
        destination = (root / str(relative_path or "")).resolve()
        relative = destination.relative_to(root).as_posix() if _is_within(destination, root) else ""
        registered = {
            folder["relative_path"]
            for folder in self.store.list_local_organize_folders(str(root))
        }
        if (
            not relative
            or relative not in registered
            or not destination.is_dir()
            or _is_within(destination, discard)
        ):
            raise ValueError("Elegí una carpeta de organización válida.")
        if not self.store.select_local_organize_folder(str(root), relative):
            raise ValueError("La carpeta de organización ya no está disponible.")
        return self.organize_folders()

    @staticmethod
    def _validate_folder_name(name: str) -> str:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Escribí un nombre para la carpeta.")
        if clean_name in {".", ".."} or clean_name.endswith((".", " ")):
            raise ValueError("Ese nombre de carpeta no es válido.")
        if len(clean_name) > 80:
            raise ValueError("El nombre de la carpeta es demasiado largo.")
        if any(character in INVALID_FOLDER_CHARACTERS or ord(character) < 32 for character in clean_name):
            raise ValueError("El nombre contiene caracteres que Windows no permite.")
        if clean_name.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise ValueError("Ese nombre está reservado por Windows.")
        if clean_name.casefold() in {
            DISCARD_FOLDER_NAME.casefold(),
            *(name.casefold() for name in LEGACY_DISCARD_FOLDER_NAMES),
            PRINT_FOLDER_NAME.casefold(),
        }:
            raise ValueError("Ese nombre está reservado para una carpeta administrada por la aplicación.")
        return clean_name

    def decide(
        self,
        item_id: str,
        decision: str,
        destination_relative_path: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"pending", "keep", "delete", "organize", "print"}:
            raise ValueError("Decisión inválida.")
        item = self.get_item(item_id)
        library = self.store.get_local_library()
        if not item or not library:
            raise FileNotFoundError("Archivo no encontrado.")

        root = Path(library["root_path"]).resolve()
        discard = Path(library["discard_path"]).resolve()
        print_root = (root / PRINT_FOLDER_NAME).resolve()
        source = Path(item["current_path"]).resolve(strict=True)
        if not source.is_file() or not _is_within(source, root):
            raise FileNotFoundError("El archivo ya no está disponible.")

        current_decision = item["decision"]
        stored_decision = "keep" if decision == "print" else decision
        new_path = source
        new_relative: str | None = None
        print_copy_relative_path: str | None = item.get("print_copy_relative_path")
        update_print_copy = False
        created_print_copy: Path | None = None
        removed_print_copy: Path | None = None

        if decision == "print":
            if item["type"] != "IMAGE":
                raise ValueError("La carpeta A imprimir acepta solamente imágenes.")
            if current_decision != "pending":
                raise ValueError("Esta imagen ya tiene una decisión.")
            if not _is_within(print_root, root) or _is_within(print_root, discard):
                raise ValueError("La carpeta A imprimir no es segura.")
            print_root.mkdir(parents=False, exist_ok=True)
            destination = _unique_destination(print_root / source.name)
            created_print_copy = Path(shutil.copy2(str(source), str(destination))).resolve()
            if not _is_within(created_print_copy, print_root):
                created_print_copy.unlink(missing_ok=True)
                raise ValueError("La copia para imprimir quedó fuera de la carpeta permitida.")
            print_copy_relative_path = created_print_copy.relative_to(root).as_posix()
            update_print_copy = True
        elif decision == "delete" and current_decision != "delete":
            relative = Path(item["original_relative_path"])
            destination = (discard / relative).resolve()
            if not _is_within(destination, discard):
                raise ValueError("La ruta de destino no es segura.")
            destination = _unique_destination(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            new_path = Path(shutil.move(str(source), str(destination))).resolve()
        elif decision == "organize" and current_decision != "organize":
            folders = self.organize_folders()
            selected = destination_relative_path or folders["selected"]
            allowed = {folder["relativePath"] for folder in folders["folders"]}
            if not selected or selected not in allowed:
                raise ValueError("Elegí una carpeta antes de mover con la flecha hacia arriba.")
            organize_root = (root / selected).resolve()
            if not _is_within(organize_root, root) or _is_within(organize_root, discard):
                raise ValueError("La carpeta de organización no es segura.")
            destination = _unique_destination(organize_root / Path(item["original_relative_path"]).name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            new_path = Path(shutil.move(str(source), str(destination))).resolve()
        elif decision not in {"delete", "organize"} and current_decision in {"delete", "organize"}:
            destination = (root / Path(item["original_relative_path"])).resolve()
            if not _is_within(destination, root) or _is_within(destination, discard):
                raise ValueError("La ruta de restauración no es segura.")
            destination = _unique_destination(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            new_path = Path(shutil.move(str(source), str(destination))).resolve()
            new_relative = new_path.relative_to(root).as_posix()

        if decision == "pending" and print_copy_relative_path:
            print_copy = (root / print_copy_relative_path).resolve()
            if not _is_within(print_copy, print_root):
                raise ValueError("La copia para imprimir registrada no es segura.")
            if print_copy.exists():
                if not print_copy.is_file():
                    raise ValueError("La copia para imprimir ya no es un archivo válido.")
                print_copy.unlink()
                removed_print_copy = print_copy
            print_copy_relative_path = None
            update_print_copy = True

        try:
            updated = self.store.update_local_media(
                item_id,
                stored_decision,
                current_path=str(new_path),
                original_relative_path=new_relative,
                **(
                    {"print_copy_relative_path": print_copy_relative_path}
                    if update_print_copy
                    else {}
                ),
            )
        except Exception:
            if created_print_copy:
                created_print_copy.unlink(missing_ok=True)
            if removed_print_copy and not removed_print_copy.exists():
                shutil.copy2(str(source), str(removed_print_copy))
            raise
        if not updated:
            if created_print_copy:
                created_print_copy.unlink(missing_ok=True)
            if removed_print_copy and not removed_print_copy.exists():
                shutil.copy2(str(source), str(removed_print_copy))
            raise FileNotFoundError("Archivo no encontrado.")
        return self.get_item(item_id) or {}
