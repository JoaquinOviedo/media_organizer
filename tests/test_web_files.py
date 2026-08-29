import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebFilesTest(unittest.TestCase):
    def test_media_viewer_adapts_to_source_orientation(self):
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("setMediaLayout(image.naturalWidth, image.naturalHeight)", app)
        self.assertIn("setMediaLayout(video.videoWidth, video.videoHeight)", app)
        self.assertIn('card.classList.add("media-portrait")', app)
        self.assertIn('card.classList.add("media-landscape")', app)
        self.assertIn('card.classList.add("media-square")', app)
        self.assertIn(".media-card.media-portrait", styles)
        self.assertIn(".media-card.media-landscape", styles)
        self.assertIn(".media-card.media-square", styles)
        self.assertIn("object-fit: contain", styles)

    def test_keyboard_flow_includes_organize_and_undo(self):
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('ArrowLeft: () => decide("delete")', app)
        self.assertIn('ArrowRight: () => decide("keep")', app)
        self.assertIn('ArrowUp: () => decide("organize")', app)
        self.assertIn("ArrowDown: undo", app)
        self.assertIn('id="destinationFolderSelect"', page)
        self.assertIn('id="newFolderName"', page)
        self.assertIn('id="organizeButton"', page)


if __name__ == "__main__":
    unittest.main()
