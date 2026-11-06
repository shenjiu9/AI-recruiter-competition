import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Crypto:
    def __init__(self, key: str):
        self.cipher = AESGCM(base64.urlsafe_b64decode(key))

    def encrypt(self, value: dict, purpose: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self.cipher.encrypt(
            nonce, json.dumps(value, ensure_ascii=False).encode(), purpose.encode()
        )

    def decrypt(self, value: bytes, purpose: str) -> dict:
        return json.loads(self.cipher.decrypt(value[:12], value[12:], purpose.encode()))
