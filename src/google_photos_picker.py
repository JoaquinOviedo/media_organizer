import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests


AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
PICKER_API = "https://photospicker.googleapis.com/v1"
SCOPES = (
    "openid email profile "
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
)


class GooglePhotosError(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthAttempt:
    state: str
    verifier: str
    authorization_url: str


class GooglePhotosPickerClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def create_authorization_attempt(self) -> OAuthAttempt:
        if not self.configured:
            raise GooglePhotosError("Faltan las credenciales OAuth de Google.")

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return OAuthAttempt(
            state=state,
            verifier=verifier,
            authorization_url=f"{AUTHORIZATION_URL}?{urlencode(params)}",
        )

    def exchange_code(self, code: str, verifier: str) -> dict[str, Any]:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            },
            timeout=20,
        )
        payload = self._json_or_raise(response, "No se pudo completar la conexion con Google")
        return self._with_expiration(payload)

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        payload = self._json_or_raise(response, "No se pudo renovar la conexion con Google")
        payload.setdefault("refresh_token", refresh_token)
        return self._with_expiration(payload)

    def user_info(self, access_token: str) -> dict[str, Any]:
        response = requests.get(
            USERINFO_URL,
            headers=self._headers(access_token),
            timeout=20,
        )
        return self._json_or_raise(response, "No se pudo obtener la cuenta conectada")

    def create_picker_session(self, access_token: str, max_item_count: int = 200) -> dict[str, Any]:
        response = requests.post(
            f"{PICKER_API}/sessions",
            headers={**self._headers(access_token), "Content-Type": "application/json"},
            json={"pickingConfig": {"maxItemCount": str(max_item_count)}},
            timeout=20,
        )
        return self._json_or_raise(response, "No se pudo abrir Google Photos Picker")

    def get_picker_session(self, access_token: str, session_id: str) -> dict[str, Any]:
        response = requests.get(
            f"{PICKER_API}/sessions/{session_id}",
            headers=self._headers(access_token),
            timeout=20,
        )
        return self._json_or_raise(response, "No se pudo consultar la seleccion")

    def list_media_items(self, access_token: str, session_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = {"sessionId": session_id, "pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(
                f"{PICKER_API}/mediaItems",
                headers=self._headers(access_token),
                params=params,
                timeout=30,
            )
            payload = self._json_or_raise(response, "No se pudieron recuperar las fotos elegidas")
            items.extend(payload.get("mediaItems", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                return items

    def download_preview(self, access_token: str, base_url: str, media_type: str) -> requests.Response:
        # Para videos se solicita una miniatura sin el icono superpuesto de Google.
        suffix = "=w1600-h1600-no" if media_type == "VIDEO" else "=w1600-h1600"
        response = requests.get(
            f"{base_url}{suffix}",
            headers=self._headers(access_token),
            timeout=45,
        )
        if not response.ok:
            raise GooglePhotosError(f"No se pudo cargar la vista previa ({response.status_code}).")
        return response

    def stream_video(
        self,
        access_token: str,
        base_url: str,
        range_header: str | None = None,
    ) -> requests.Response:
        headers = self._headers(access_token)
        if range_header:
            headers["Range"] = range_header
        response = requests.get(
            f"{base_url}=dv",
            headers=headers,
            timeout=60,
            stream=True,
        )
        if not response.ok:
            response.close()
            raise GooglePhotosError(f"No se pudo cargar el video ({response.status_code}).")
        return response

    @staticmethod
    def _headers(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    @staticmethod
    def _json_or_raise(response: requests.Response, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not response.ok:
            error = payload.get("error", {})
            nested_detail = error.get("message") if isinstance(error, dict) else error
            detail = payload.get("error_description") or nested_detail
            raise GooglePhotosError(f"{context}: {detail or response.status_code}")
        return payload

    @staticmethod
    def _with_expiration(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        expires_in = int(normalized.get("expires_in") or 3600)
        normalized["expires_at"] = int(time.time()) + expires_in
        return normalized
