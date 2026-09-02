import tempfile
import unittest
from pathlib import Path

from src.local_media import DISCARD_FOLDER_NAME, PRINT_FOLDER_NAME, LocalMediaLibrary
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
        self.assertEqual(Path(restored["current_path"]).resolve(), original.resolve())
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

    def test_organize_moves_to_selected_folder_and_pending_restores(self):
        source_folder = self.root / "sin ordenar"
        source_folder.mkdir()
        original = source_folder / "cumple.jpg"
        original.write_bytes(b"photo")
        self.library.scan(self.root)
        item = self.library.list_items()[0]

        folders = self.library.create_organize_folder("Familia")
        moved = self.library.decide(
            item["item_id"],
            "organize",
            destination_relative_path=folders["selected"],
        )

        self.assertFalse(original.exists())
        self.assertEqual(
            Path(moved["current_path"]).parent.resolve(),
            (self.root / "Familia").resolve(),
        )
        self.assertEqual(moved["decision"], "organize")

        status = self.library.scan(self.root)
        self.assertEqual(status["total"], 1)
        self.assertEqual(self.library.list_items()[0]["decision"], "organize")

        restored = self.library.decide(item["item_id"], "pending")
        self.assertTrue(original.exists())
        self.assertEqual(Path(restored["current_path"]).resolve(), original.resolve())

    def test_print_copies_image_marks_keep_and_undo_removes_copy(self):
        source_folder = self.root / "familia"
        source_folder.mkdir()
        original = source_folder / "cumple.jpg"
        original.write_bytes(b"photo-to-print")
        print_folder = self.root / PRINT_FOLDER_NAME
        print_folder.mkdir()
        existing_copy = print_folder / "cumple.jpg"
        existing_copy.write_bytes(b"existing-print")
        self.library.scan(self.root)
        item = self.library.list_items()[0]

        printed = self.library.decide(item["item_id"], "print")
        copy_path = self.root / printed["print_copy_relative_path"]

        self.assertTrue(original.exists())
        self.assertTrue(copy_path.exists())
        self.assertEqual(copy_path.parent, self.root / PRINT_FOLDER_NAME)
        self.assertEqual(copy_path.read_bytes(), original.read_bytes())
        self.assertNotEqual(copy_path, existing_copy)
        self.assertEqual(existing_copy.read_bytes(), b"existing-print")
        self.assertEqual(printed["decision"], "keep")

        rescanned = self.library.scan(self.root)
        self.assertEqual(rescanned["total"], 1)

        restored = self.library.decide(item["item_id"], "pending")
        self.assertTrue(original.exists())
        self.assertFalse(copy_path.exists())
        self.assertTrue(existing_copy.exists())
        self.assertEqual(restored["decision"], "pending")
        self.assertIsNone(restored["print_copy_relative_path"])

    def test_print_rejects_video(self):
        video = self.root / "clip.mp4"
        video.write_bytes(b"video")
        self.library.scan(self.root)
        item = self.library.list_items()[0]

        with self.assertRaises(ValueError):
            self.library.decide(item["item_id"], "print")

        self.assertFalse((self.root / PRINT_FOLDER_NAME).exists())

    def test_created_organize_folders_are_saved_and_preselected(self):
        self.library.scan(self.root)

        first = self.library.create_organize_folder("Familia")
        second = self.library.create_organize_folder("Viajes")
        selected = self.library.select_organize_folder("Familia")

        self.assertEqual(first["selected"], "Familia")
        self.assertEqual(second["selected"], "Viajes")
        self.assertEqual(selected["selected"], "Familia")
        self.assertEqual(
            {folder["name"] for folder in selected["folders"]},
            {"Familia", "Viajes"},
        )

    def test_organize_folder_name_cannot_escape_the_library(self):
        self.library.scan(self.root)

        with self.assertRaises(ValueError):
            self.library.create_organize_folder("../afuera")

    def test_old_later_decisions_return_to_the_pending_queue(self):
        original = self.root / "pendiente.jpg"
        original.write_bytes(b"photo")
        self.library.scan(self.root)
        item = self.library.list_items()[0]
        self.store.update_local_media(item["item_id"], "later")

        reopened = MvpStore(self.store.database_path)

        self.assertEqual(reopened.get_local_media(item["item_id"])["decision"], "pending")


if __name__ == "__main__":
    unittest.main()
