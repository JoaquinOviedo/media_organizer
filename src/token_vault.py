import json
from threading import Lock
from typing import Any

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


class TokenVaultError(RuntimeError):
    pass


class PersistentTokenVault:
    """Guarda el token mínimo necesario en el almacén seguro del sistema operativo."""

    def __init__(
        self,
        # Identificador histórico: cambiarlo cerraría sesiones ya guardadas.
        service: str = "SwipeClean.GooglePhotos",
        account: str = "default",
        backend: Any | None = None,
    ):
        self.service = service
        self.account = account
        self.backend = backend or keyring
        self._cache: dict[str, Any] | None = None
        self._loaded = False
        self._lock = Lock()

    def get(self) -> dict[str, Any] | None:
        with self._lock:
            if self._loaded:
                return dict(self._cache) if self._cache else None
            try:
                raw = self.backend.get_password(self.service, self.account)
            except KeyringError as error:
                raise TokenVaultError("Windows no pudo leer la sesion guardada.") from error
            self._loaded = True
            if not raw:
                self._cache = None
                return None
            try:
                token = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as error:
                raise TokenVaultError("La sesion guardada esta dañada.") from error
            self._cache = token
            return dict(token)

    def save(self, token: dict[str, Any]) -> None:
        safe_token = {
            key: token[key]
            for key in (
                "access_token",
                "refresh_token",
                "expires_at",
                "expires_in",
                "scope",
                "token_type",
                "user",
            )
            if key in token
        }
        try:
            self.backend.set_password(
                self.service,
                self.account,
                json.dumps(safe_token, separators=(",", ":")),
            )
        except KeyringError as error:
            raise TokenVaultError("Windows no pudo guardar la sesion de Google.") from error
        with self._lock:
            self._cache = safe_token
            self._loaded = True

    def clear(self) -> None:
        try:
            self.backend.delete_password(self.service, self.account)
        except PasswordDeleteError:
            pass
        except KeyringError as error:
            raise TokenVaultError("Windows no pudo borrar la sesion guardada.") from error
        with self._lock:
            self._cache = None
            self._loaded = True
