import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.mvp_store import MvpStore


class MvpStoreTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MvpStore(Path(self.tempdir.name) / "test.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_picker_items_are_upserted_without_losing_decision(self):
        item = {
            "id": "photo-1",
            "type": "PHOTO",
            "createTime": "2026-08-25T18:00:00Z",
            "mediaFile": {
                "filename": "foto.jpg",
                "baseUrl": "https://example.test/base",
                "mimeType": "image/jpeg",
                "mediaFileMetadata": {"width": 1200, "height": 900},
            },
        }
        self.store.upsert_picker_items("session-1", [item])
        self.assertTrue(self.store.set_media_decision("photo-1", "delete"))
        self.store.upsert_picker_items("session-2", [item])

        stored = self.store.get_media("photo-1")
        self.assertEqual(stored["decision"], "delete")
        self.assertEqual(stored["picker_session_id"], "session-2")

    def test_extension_decision_is_idempotent(self):
        self.store.record_extension_decision(
            "google-id", "https://photos.google.com/photo/google-id", "delete", "pending"
        )
        self.store.record_extension_decision(
            "google-id", "https://photos.google.com/photo/google-id", "delete", "added"
        )

        decisions = self.store.list_extension_decisions()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["album_status"], "added")

    def test_video_metadata_is_preserved_for_playback(self):
        item = {
            "id": "video-1",
            "type": "VIDEO",
            "createTime": "2026-08-25T18:00:00Z",
            "mediaFile": {
                "filename": "video.mp4",
                "baseUrl": "https://example.test/video",
                "mimeType": "video/mp4",
                "mediaFileMetadata": {
                    "width": 1920,
                    "height": 1080,
                    "videoMetadata": {"status": "READY", "fps": 30},
                },
            },
        }

        self.store.upsert_picker_items("session-video", [item])

        stored = self.store.get_media("video-1")
        self.assertEqual(stored["type"], "VIDEO")
        self.assertEqual(stored["mime_type"], "video/mp4")
        self.assertIn('"status": "READY"', stored["metadata_json"])

    def test_existing_local_database_gets_print_copy_column(self):
        database_path = Path(self.tempdir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                """
                CREATE TABLE local_media_items (
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
                    available INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        MvpStore(database_path)

        connection = sqlite3.connect(database_path)
        try:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(local_media_items)")
            }
        finally:
            connection.close()
        self.assertIn("print_copy_relative_path", columns)


if __name__ == "__main__":
    unittest.main()
