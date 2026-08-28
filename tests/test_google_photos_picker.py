import unittest
from unittest.mock import Mock, patch

from src.google_photos_picker import GooglePhotosPickerClient


class GooglePhotosPickerClientTest(unittest.TestCase):
    def setUp(self):
        self.client = GooglePhotosPickerClient(
            "client-id", "client-secret", "http://127.0.0.1:8765/auth/google/callback"
        )

    def test_authorization_uses_picker_scope_and_pkce(self):
        attempt = self.client.create_authorization_attempt()
        self.assertIn("photospicker.mediaitems.readonly", attempt.authorization_url)
        self.assertIn("code_challenge_method=S256", attempt.authorization_url)
        self.assertTrue(attempt.state)
        self.assertTrue(attempt.verifier)

    @patch("src.google_photos_picker.requests.get")
    def test_list_media_items_follows_pagination(self, get):
        first = Mock(ok=True)
        first.json.return_value = {"mediaItems": [{"id": "1"}], "nextPageToken": "next"}
        second = Mock(ok=True)
        second.json.return_value = {"mediaItems": [{"id": "2"}]}
        get.side_effect = [first, second]

        items = self.client.list_media_items("token", "session")

        self.assertEqual([item["id"] for item in items], ["1", "2"])
        self.assertEqual(get.call_count, 2)

    @patch("src.google_photos_picker.requests.post")
    def test_refresh_access_token_keeps_refresh_token_and_expiration(self, post):
        response = Mock(ok=True)
        response.json.return_value = {"access_token": "new-token", "expires_in": 3600}
        post.return_value = response

        token = self.client.refresh_access_token("saved-refresh-token")

        self.assertEqual(token["refresh_token"], "saved-refresh-token")
        self.assertGreater(token["expires_at"], 0)
        request_data = post.call_args.kwargs["data"]
        self.assertEqual(request_data["grant_type"], "refresh_token")

    @patch("src.google_photos_picker.requests.get")
    def test_video_stream_uses_dv_and_forwards_range(self, get):
        response = Mock(ok=True)
        get.return_value = response

        streamed = self.client.stream_video("token", "https://example.test/base", "bytes=0-999")

        self.assertIs(streamed, response)
        self.assertEqual(get.call_args.args[0], "https://example.test/base=dv")
        self.assertEqual(get.call_args.kwargs["headers"]["Range"], "bytes=0-999")
        self.assertTrue(get.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
