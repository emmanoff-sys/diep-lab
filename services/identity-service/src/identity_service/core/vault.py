"""Vault HTTP client — AppRole auth + PKI certificate issuance for RS256 JWT signing.

Authentication path (ADR-008):
  1. Read role-id and secret-id from tmpfs /run/reos/identity-service/ (Vault agent drops them)
  2. POST /v1/auth/{approle_mount}/login → client_token
  3. POST /v1/{pki_mount}/issue/{pki_role} → certificate + private_key (exported RSA-4096)

The private key is held in memory only and never written to disk.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
from identity_service.config import settings

logger = logging.getLogger(__name__)


class VaultError(Exception):
    pass


class VaultClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._http = httpx.AsyncClient(
            base_url=settings.VAULT_ADDR,
            timeout=10.0,
            verify=True,  # TLS verification mandatory — ADR-008
        )

    async def _read_credential_file(self, path: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: Path(path).read_text().strip())

    async def authenticate(self) -> None:
        role_id = await self._read_credential_file(settings.VAULT_ROLE_ID_FILE)
        secret_id = await self._read_credential_file(settings.VAULT_SECRET_ID_FILE)

        resp = await self._http.post(
            f"/v1/auth/{settings.VAULT_APPROLE_MOUNT}/login",
            json={"role_id": role_id, "secret_id": secret_id},
        )
        if resp.status_code != 200:
            raise VaultError(f"Vault AppRole login failed: {resp.status_code} {resp.text}")

        data: dict[str, Any] = resp.json()
        self._token = data["auth"]["client_token"]
        logger.info("vault.authenticated")

    async def issue_jwt_signing_key(self) -> dict[str, str]:
        """Issue an RSA-4096 certificate + private key from Vault PKI.

        Returns dict with keys: certificate, private_key, serial_number, expiration.
        The returned private_key is PEM-encoded RSA-4096.
        The TTL is 720h (30 days) matching the 30-day key rotation requirement.
        """
        if not self._token:
            await self.authenticate()

        token = self._token
        if token is None:
            raise VaultError("Vault authentication did not return a client token")

        resp = await self._http.post(
            f"/v1/{settings.VAULT_PKI_MOUNT}/issue/{settings.VAULT_PKI_ROLE}",
            json={
                "common_name": "identity-service-jwt",
                "ttl": "720h",  # 30 days
                "key_type": "rsa",
                "key_bits": 4096,
            },
            headers={"X-Vault-Token": token},
        )

        if resp.status_code == 403:
            # Token may have expired — re-authenticate once and retry
            await self.authenticate()
            token = self._token
            if token is None:
                raise VaultError("Vault re-authentication did not return a client token")
            resp = await self._http.post(
                f"/v1/{settings.VAULT_PKI_MOUNT}/issue/{settings.VAULT_PKI_ROLE}",
                json={
                    "common_name": "identity-service-jwt",
                    "ttl": "720h",
                    "key_type": "rsa",
                    "key_bits": 4096,
                },
                headers={"X-Vault-Token": token},
            )

        if resp.status_code != 200:
            raise VaultError(f"Vault PKI issue failed: {resp.status_code} {resp.text}")

        data: dict[str, Any] = resp.json()
        return {
            "certificate": data["data"]["certificate"],
            "private_key": data["data"]["private_key"],
            "serial_number": data["data"]["serial_number"],
            "expiration": str(data["data"]["expiration"]),
        }

    async def close(self) -> None:
        await self._http.aclose()
