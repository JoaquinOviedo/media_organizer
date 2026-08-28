import tempfile
import unittest
from pathlib import Path

from src.local_media import DISCARD_FOLDER_NAME, LocalMediaLibrary
from src.mvp_store import MvpStore


class LocalMediaLibraryTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "biblioteca"
        self.root.mkdir()
        self.store = MvpStore(Path(self.tempdir.name) / "test.sqlite3")
        self.library = LocalMediaLibrary(self.store)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_scan_is_recursive_and_includes_audio(self):
        nested = self.root / "viaje" / "dia 1"
        nested.mkdir(parents=True)
        (nested / "foto.jpg").write_bytes(b"photo")
        (nested / "video.mp4").write_bytes(b"video")
        (nested / "nota.mp3").write_bytes(b"audio")
        (nested / "ignorar.txt").write_text("texto", encoding="utf-8")

        status = self.library.scan(self.root)
        items = self.library.list_items()

        self.assertEqual(status["total"], 3)
        self.assertEqual({item["type"] for item in items}, {"IMAGE", "VIDEO", "AUDIO"})
        self.assertTrue(all("viaje/dia 1" in item["original_relative_path"] for item in items))

    def test_delete_moves_and_pending_restores_the_file(self):
        nested = self.root / "familia"
        nested.mkdir()
        original = nested / "foto.jpg"
        original.write_bytes(b"photo")
        self.library.scan(self.root)
        item = self.library.list_items()[0]

        moved = self.library.decide(item["item_id"], "delete")
        moved_path = Path(moved["current_path"])

        self.assertFalse(original.exists())
        self.assertTrue(moved_path.exists())
        self.assertIn(DISCARD_FOLDER_NAME, moved_path.parts)
        self.assertEqual(moved["decision"], "delete")

        restored = self.library.decide(item["item_id"], "pending")

        self.assertTrue(original.exists())
        self.assertEqual(Path(restored["current_path"]), original)
        self.assertEqual(restored["decision"], "pending")

    def test_rescan_does_not_reimport_discarded_files(self):
        original = self.root / "foto.jpg"
        original.write_bytes(b"photo")
        self.library.scan(self.root)
        item = self.library.list_items()[0]
        self.library.decide(item["item_id"], "delete")

        status = self.library.scan(self.root)
        items = self.library.list_items()

        self.assertEqual(status["total"], 1)
        self.assertEqual(items[0]["decision"], "delete")

    def test_scan_excludes_the_legacy_discard_folder(self):
        legacy = self.root / "_SwipeClean_Para_Eliminar"
        legacy.mkdir()
        (legacy / "descartada.jpg").write_bytes(b"photo")
        (self.root / "conservar.jpg").write_bytes(b"photo")

        status = self.library.scan(self.root)

        self.assertEqual(status["total"], 1)
        self.assertEqual(self.library.list_items()[0]["filename"], "conservar.jpg")


if __name__ == "__main__":
    unittest.main()
