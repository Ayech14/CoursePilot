"""Encryption for calendar links, which carry a private token (PRD L3).

A link like eClass's `...?authtoken=...` lets anyone holding it read the student's calendar, so it
is stored encrypted with Fernet (AES-128-CBC with an HMAC-SHA256 check). The database alone is then
not enough to read it: the key lives in the environment.

Fernet output differs every time, so a keyed digest (HMAC-SHA256) of the link is stored as well,
to tell that the same calendar is already connected without decrypting every link.
"""

import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings, get_settings


class LinkCipher:
    def __init__(self, master_key: bytes) -> None:
        self._fernet = Fernet(base64.urlsafe_b64encode(_derive(master_key, b"encrypt")))
        self._mac_key = _derive(master_key, b"digest")

    def encrypt(self, link: str) -> str:
        return self._fernet.encrypt(link.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ValueError(
                "Calendar link could not be decrypted; check CALENDAR_LINK_KEY"
            ) from exc

    def digest(self, link: str) -> str:
        return hmac.new(self._mac_key, link.encode(), hashlib.sha256).hexdigest()


def _derive(master_key: bytes, purpose: bytes) -> bytes:
    """Separate 32-byte keys for encrypting and for the digest, both from one secret."""
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"coursepilot-calendar-" + purpose
    ).derive(master_key)


def master_key(settings: Settings) -> bytes:
    # Production must set its own key (see Settings). Elsewhere the JWT secret stands in, so local
    # development and tests need no extra setup.
    secret = settings.calendar_link_key or settings.jwt_secret
    return secret.get_secret_value().encode()


@lru_cache
def link_cipher() -> LinkCipher:
    return LinkCipher(master_key(get_settings()))
