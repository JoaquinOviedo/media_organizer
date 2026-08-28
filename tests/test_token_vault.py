import json
import unittest

from keyring.errors import PasswordDeleteError

from src.token_vault import PersistentTokenVault


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, password):
        self.values[(service, account)] = password

    def delete_password(self, service, account):
        try:
            del self.values[(service, account)]
        except KeyError as error:
            raise PasswordDeleteError("missing") from error


class PersistentTokenVaultTest(unittest.TestCase):
    def setUp(self):
        self.backend = FakeKeyring()

    def test_token_survives_a_new_vault_instance(self):
        first = PersistentTokenVault(backend=self.backend)
        first.save(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 123456,
                "user": {"name": "Test User"},
                "id_token": "must-not-be-persisted",
            }
        )

        second = PersistentTokenVault(backend=self.backend)
        stored = second.get()

        self.assertEqual(stored["refresh_token"], "refresh")
        self.assertNotIn("id_token", stored)
        raw = next(iter(self.backend.values.values()))
        self.assertNotIn("must-not-be-persisted", raw)
        self.assertEqual(json.loads(raw)["user"]["name"], "Test User")

    def test_clear_removes_persisted_token(self):
        vault = PersistentTokenVault(backend=self.backend)
        vault.save({"access_token": "access", "refresh_token": "refresh"})

        vault.clear()

        self.assertIsNone(PersistentTokenVault(backend=self.backend).get())


if __name__ == "__main__":
    unittest.main()
