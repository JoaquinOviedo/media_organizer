import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExtensionFilesTest(unittest.TestCase):
    def test_background_relays_local_requests(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
        background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
        content = (ROOT / "extension" / "content.js").read_text(encoding="utf-8")

        self.assertEqual(manifest["name"], "Photo Swipper Filter para Google Photos")
        self.assertEqual(manifest["version"], "0.4.1")
        self.assertEqual(manifest["background"]["service_worker"], "background.js")
        self.assertEqual(manifest["content_scripts"][0]["run_at"], "document_start")
        self.assertIn("http://127.0.0.1:8765/*", manifest["host_permissions"])
        self.assertIn('swipeclean:heartbeat', background)
        self.assertIn('swipeclean:record', background)
        self.assertIn('sendToSwipeClean("swipeclean:heartbeat")', content)
        self.assertIn('window.addEventListener("keydown", handleKeyboardDecision, true)', content)
        self.assertIn("event.stopImmediatePropagation()", content)
        self.assertIn('document.querySelectorAll(\'button, [role="button"]\')', content)
        self.assertIn("goToOlderPhoto(currentId)", content)
        self.assertIn("Mostrando la siguiente foto, normalmente más antigua", content)
        self.assertNotIn('fetch(`${SERVER}', content)


if __name__ == "__main__":
    unittest.main()
