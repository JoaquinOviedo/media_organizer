import time
import unittest
from unittest.mock import Mock, patch

import mvp_app


class MvpAppTest(unittest.TestCase):
    def setUp(self):
        self.client = mvp_app.app.test_client()

    def test_media_filter_returns_only_local_delete_queue(self):
        items = [
            {"item_id": "one", "decision": "delete"},
            {"item_id": "two", "decision": "keep"},
        ]
        with patch.object(mvp_app.store, "list_media", return_value=items):
            response = self.client.get("/api/media?decision=delete")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["item_id"] for item in response.get_json()["items"]], ["one"])

    def test_video_route_streams_bytes_and_forwards_range(self):
        item = {
            "item_id": "video-one",
            "type": "VIDEO",
            "mime_type": "video/mp4",
            "base_url": "https://example.test/video",
        }
        remote = Mock()
        remote.ok = True
        remote.status_code = 206
        remote.headers = {
            "Content-Type": "video/mp4",
            "Content-Length": "6",
            "Content-Range": "bytes 0-5/6",
            "Accept-Ranges": "bytes",
        }
        remote.iter_content.return_value = iter([b"abc", b"def"])
        token = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": int(time.time()) + 3600,
        }

        with (
            patch.object(mvp_app.store, "get_media", return_value=item),
            patch.object(mvp_app.token_vault, "get", return_value=token),
            patch.object(mvp_app.google, "stream_video", return_value=remote) as stream_video,
        ):
            response = self.client.get(
                "/api/media/video-one/video",
                headers={"Range": "bytes=0-5"},
            )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b"abcdef")
        self.assertEqual(response.headers["Content-Range"], "bytes 0-5/6")
        stream_video.assert_called_once_with(
            "access", "https://example.test/video", "bytes=0-5"
        )
        remote.close.assert_called_once()

    def test_local_decision_returns_moved_item_and_status(self):
        moved = {"item_id": "local-one", "decision": "delete"}
        with (
            patch.object(mvp_app.local_library, "decide", return_value=moved) as decide,
            patch.object(
                mvp_app.local_library,
                "status",
                return_value={"counts": {"delete": 1}},
            ),
        ):
            response = self.client.post(
                "/api/local/media/local-one/decision",
                json={"decision": "delete"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["item"], moved)
        decide.assert_called_once_with("local-one", "delete")


if __name__ == "__main__":
    unittest.main()
