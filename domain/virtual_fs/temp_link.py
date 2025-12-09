from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException

from domain.config.service import ConfigService

from .processing import VirtualFSProcessingMixin


class VirtualFSTempLinkMixin(VirtualFSProcessingMixin):
    @classmethod
    async def get_temp_link_secret_key(cls) -> bytes:
        return await ConfigService.get_secret_key("TEMP_LINK_SECRET_KEY", None)

    @classmethod
    async def generate_temp_link_token(cls, path: str, expires_in: int = 3600) -> str:
        if expires_in <= 0:
            expiration_time = "0"
        else:
            expiration_time = str(int(time.time() + expires_in))

        message = f"{path}:{expiration_time}".encode("utf-8")
        secret_key = await cls.get_temp_link_secret_key()
        signature = hmac.new(secret_key, message, hashlib.sha256).digest()

        token_data = f"{path}:{expiration_time}:{base64.urlsafe_b64encode(signature).decode('utf-8')}"
        return base64.urlsafe_b64encode(token_data.encode("utf-8")).decode("utf-8")

    @classmethod
    async def verify_temp_link_token(cls, token: str) -> str:
        try:
            decoded_token = base64.urlsafe_b64decode(token).decode("utf-8")
            path, expiration_time_str, signature_b64 = decoded_token.rsplit(":", 2)
            signature = base64.urlsafe_b64decode(signature_b64)
        except (ValueError, TypeError, base64.binascii.Error):
            raise HTTPException(status_code=400, detail="Invalid token format")

        if expiration_time_str != "0":
            expiration_time = int(expiration_time_str)
            if time.time() > expiration_time:
                raise HTTPException(status_code=410, detail="Link has expired")

        message = f"{path}:{expiration_time_str}".encode("utf-8")
        secret_key = await cls.get_temp_link_secret_key()
        expected_signature = hmac.new(secret_key, message, hashlib.sha256).digest()

        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        return path
