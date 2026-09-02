import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


_PRINT_COPY_UNCHANGED = object()


class MvpStore:
    """Persistencia local de medios y decisiones; nunca guarda tokens OAuth."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS media_items (
                    item_id TEXT PRIMARY KEY,
                    picker_session_id TEXT,
                    type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    create_time TEXT,
                    base_url TEXT,
                    mime_type TEXT,
                    width INTEGER,
                    height INTEGER,
                    decision TEXT NOT NULL DEFAULT 'pending',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS extension_decisions (
                    photo_id TEXT PRIMARY KEY,
                    photo_url TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    album_status TEXT NOT NULL DEFAULT 'pending',
                    message TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS local_library (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    root_path TEXT NOT NULL,
                    discard_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS local_media_items (
                    item_id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    original_relative_path TEXT NOT NULL,
                    current_path TEXT NOT NULL,
                    type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type TEXT,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    modified_at REAL,
                    decision TEXT NOT NULL DEFAULT 'pending',
                    print_copy_relative_path TEXT,
                    available INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_local_media_root
                ON local_media_items(root_path, available, decision);

                CREATE TABLE IF NOT EXISTS local_organize_folders (
                    root_path TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (root_path, relative_path)
                );
                """
            )
            local_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(local_media_items)")
            }
            if "print_copy_relative_path" not in local_columns:
                connection.execute(
                    "ALTER TABLE local_media_items ADD COLUMN print_copy_relative_path TEXT"
                )
            # "Después" dejó de ser una decisión del flujo local. Los archivos
            # históricos vuelven a la cola sin mover nada en el disco.
            connection.execute(
                "UPDATE local_media_items SET decision = 'pending' WHERE decision = 'later'"
            )

    def upsert_picker_items(self, session_id: str, items: list[dict[str, Any]]) -> None:
        with self._connection() as connection:
            for item in items:
                media_file = item.get("mediaFile") or {}
                metadata = media_file.get("mediaFileMetadata") or {}
                connection.execute(
                    """
                    INSERT INTO media_items (
                        item_id, picker_session_id, type, filename, create_time,
                        base_url, mime_type, width, height, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        picker_session_id = excluded.picker_session_id,
                        type = excluded.type,
                        filename = excluded.filename,
                        create_time = excluded.create_time,
                        base_url = excluded.base_url,
                        mime_type = excluded.mime_type,
                        width = excluded.width,
                        height = excluded.height,
                        metadata_json = excluded.metadata_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        item["id"],
                        session_id,
                        item.get("type", "TYPE_UNSPECIFIED"),
                        media_file.get("filename", "Sin nombre"),
                        item.get("createTime"),
                        media_file.get("baseUrl"),
                        media_file.get("mimeType"),
                        metadata.get("width"),
                        metadata.get("height"),
                        json.dumps(metadata),
                    ),
                )

    def list_media(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT item_id, type, filename, create_time, mime_type, width,
                       height, decision, updated_at
                FROM media_items
                ORDER BY COALESCE(create_time, updated_at) DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_media(self, item_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM media_items WHERE item_id = ?", (item_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_media_decision(self, item_id: str, decision: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE media_items
                SET decision = ?, updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
                """,
                (decision, item_id),
            )
        return cursor.rowcount == 1

    def record_extension_decision(
        self,
        photo_id: str,
        photo_url: str,
        decision: str,
        album_status: str,
        message: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO extension_decisions (
                    photo_id, photo_url, decision, album_status, message
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(photo_id) DO UPDATE SET
                    photo_url = excluded.photo_url,
                    decision = excluded.decision,
                    album_status = excluded.album_status,
                    message = excluded.message,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (photo_id, photo_url, decision, album_status, message),
            )

    def list_extension_decisions(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT photo_id, photo_url, decision, album_status, message, updated_at
                FROM extension_decisions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def sync_local_library(
        self,
        root_path: str,
        discard_path: str,
        items: list[dict[str, Any]],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO local_library (id, root_path, discard_path)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    root_path = excluded.root_path,
                    discard_path = excluded.discard_path,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (root_path, discard_path),
            )
            connection.execute(
                """
                UPDATE local_media_items
                SET available = 0
                WHERE root_path = ? AND decision NOT IN ('delete', 'organize')
                """,
                (root_path,),
            )
            for item in items:
                connection.execute(
                    """
                    INSERT INTO local_media_items (
                        item_id, root_path, original_relative_path, current_path,
                        type, filename, mime_type, size_bytes, modified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        root_path = excluded.root_path,
                        original_relative_path = excluded.original_relative_path,
                        current_path = excluded.current_path,
                        type = excluded.type,
                        filename = excluded.filename,
                        mime_type = excluded.mime_type,
                        size_bytes = excluded.size_bytes,
                        modified_at = excluded.modified_at,
                        decision = CASE
                            WHEN local_media_items.decision = 'delete' THEN 'pending'
                            ELSE local_media_items.decision
                        END,
                        available = 1,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        item["item_id"],
                        root_path,
                        item["original_relative_path"],
                        item["current_path"],
                        item["type"],
                        item["filename"],
                        item.get("mime_type"),
                        item.get("size_bytes", 0),
                        item.get("modified_at"),
                    ),
                )

            moved = connection.execute(
                """
                SELECT item_id, current_path
                FROM local_media_items
                WHERE root_path = ? AND decision IN ('delete', 'organize')
                """,
                (root_path,),
            ).fetchall()
            for row in moved:
                connection.execute(
                    "UPDATE local_media_items SET available = ? WHERE item_id = ?",
                    (1 if Path(row["current_path"]).is_file() else 0, row["item_id"]),
                )

    def list_local_organize_folders(self, root_path: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT relative_path, name, selected
                FROM local_organize_folders
                WHERE root_path = ?
                ORDER BY selected DESC, name COLLATE NOCASE
                """,
                (root_path,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_local_organize_folder(
        self,
        root_path: str,
        relative_path: str,
        name: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE local_organize_folders SET selected = 0 WHERE root_path = ?",
                (root_path,),
            )
            connection.execute(
                """
                INSERT INTO local_organize_folders (
                    root_path, relative_path, name, selected
                ) VALUES (?, ?, ?, 1)
                ON CONFLICT(root_path, relative_path) DO UPDATE SET
                    name = excluded.name,
                    selected = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (root_path, relative_path, name),
            )

    def select_local_organize_folder(self, root_path: str, relative_path: str) -> bool:
        with self._connection() as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM local_organize_folders
                WHERE root_path = ? AND relative_path = ?
                """,
                (root_path, relative_path),
            ).fetchone()
            if not exists:
                return False
            connection.execute(
                "UPDATE local_organize_folders SET selected = 0 WHERE root_path = ?",
                (root_path,),
            )
            connection.execute(
                """
                UPDATE local_organize_folders
                SET selected = 1, updated_at = CURRENT_TIMESTAMP
                WHERE root_path = ? AND relative_path = ?
                """,
                (root_path, relative_path),
            )
        return True

    def get_local_library(self) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT root_path, discard_path, updated_at FROM local_library WHERE id = 1"
            ).fetchone()
        return dict(row) if row else None

    def list_local_media(self) -> list[dict[str, Any]]:
        library = self.get_local_library()
        if not library:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT item_id, original_relative_path, current_path, type,
                       filename, mime_type, size_bytes, modified_at, decision,
                       print_copy_relative_path
                FROM local_media_items
                WHERE root_path = ? AND available = 1
                ORDER BY COALESCE(modified_at, 0) DESC, original_relative_path
                """,
                (library["root_path"],),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_local_media(self, item_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM local_media_items WHERE item_id = ? AND available = 1",
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_local_media(
        self,
        item_id: str,
        decision: str,
        current_path: str | None = None,
        original_relative_path: str | None = None,
        print_copy_relative_path: str | None | object = _PRINT_COPY_UNCHANGED,
    ) -> bool:
        assignments = ["decision = ?", "updated_at = CURRENT_TIMESTAMP"]
        values: list[Any] = [decision]
        if current_path is not None:
            assignments.append("current_path = ?")
            values.append(current_path)
        if original_relative_path is not None:
            assignments.append("original_relative_path = ?")
            values.append(original_relative_path)
        if print_copy_relative_path is not _PRINT_COPY_UNCHANGED:
            assignments.append("print_copy_relative_path = ?")
            values.append(print_copy_relative_path)
        values.append(item_id)
        with self._connection() as connection:
            cursor = connection.execute(
                f"UPDATE local_media_items SET {', '.join(assignments)} WHERE item_id = ?",
                values,
            )
        return cursor.rowcount == 1

    def reset_local_later(self) -> int:
        library = self.get_local_library()
        if not library:
            return 0
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE local_media_items
                SET decision = 'pending', updated_at = CURRENT_TIMESTAMP
                WHERE root_path = ? AND available = 1 AND decision = 'later'
                """,
                (library["root_path"],),
            )
        return cursor.rowcount
