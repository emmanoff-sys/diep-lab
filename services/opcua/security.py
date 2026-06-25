"""OPC UA Phase 3 — client certificates, trust store, secure channel config,
user authentication, certificate hot-reload.

The certificate/trust-store logic here uses `cryptography` directly (no
asyncua import) and is fully real — `cryptography` is actually installed in
this environment, unlike `asyncua`, so this part of Phase 3 is genuinely
exercised by tests, not faked. Only `build_security_string()`'s consumption
by `asyncua.Client.set_security_string()` (in client.py) is unverified against
a real asyncua install — see VALIDATION.md.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("diep-opcua.security")

SECURITY_POLICY_URIS = {
    "None": "http://opcfoundation.org/UA/SecurityPolicy#None",
    "Basic256Sha256": "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
}
SECURITY_MODES = ("None", "Sign", "SignAndEncrypt")


class SecurityError(ValueError):
    pass


@dataclass
class SecurityConfig:
    policy: str = "None"
    mode: str = "None"
    cert_path: str | None = None
    key_path: str | None = None
    trust_store_dir: str | None = None
    username: str | None = None
    password: str | None = None

    def __post_init__(self):
        if self.policy not in SECURITY_POLICY_URIS:
            raise SecurityError(f"unsupported security_policy {self.policy!r} (supported: {list(SECURITY_POLICY_URIS)})")
        if self.mode not in SECURITY_MODES:
            raise SecurityError(f"unsupported security_mode {self.mode!r} (supported: {SECURITY_MODES})")
        if self.policy != "None" and self.mode == "None":
            raise SecurityError(f"security_policy {self.policy!r} requires a non-None security_mode")
        if self.policy != "None" and not (self.cert_path and self.key_path):
            raise SecurityError(f"security_policy {self.policy!r} requires cert_path and key_path")

    @property
    def policy_uri(self) -> str:
        return SECURITY_POLICY_URIS[self.policy]


def build_security_string(security: SecurityConfig, server_cert_path: str | None = None) -> str | None:
    """Builds the `policy,mode,cert,key[,server_cert]` string consumed by
    `asyncua.Client.set_security_string()`. Returns None for the open/dev
    "None" policy, where no security string should be set at all."""
    if security.policy == "None":
        return None
    parts = [security.policy, security.mode, security.cert_path, security.key_path]
    if server_cert_path:
        parts.append(server_cert_path)
    return ",".join(parts)


class CertificateStore:
    """Owns the connector's own client identity (cert+key) and a directory of
    trusted server certificates. `reload_if_changed()` is polled by a
    background task (see client.py) so a cert rotated on disk takes effect on
    the *next* reconnect without restarting the process — OPC UA secure
    channels are bound to the cert at channel-establishment time, so a swap
    mid-channel isn't meaningful; "without restart" means without restarting
    the connector process, not without ever re-establishing the channel."""

    def __init__(self, cert_path: str, key_path: str, trust_store_dir: str | None = None):
        self.cert_path = cert_path
        self.key_path = key_path
        self.trust_store_dir = trust_store_dir
        self._cert_mtime: float | None = None
        self._cert_pem: bytes | None = None
        self._key_pem: bytes | None = None
        self._x509_cert = None

    def ensure_self_signed_cert(self, common_name: str = "diep-opcua-connector", valid_days: int = 825) -> None:
        if os.path.exists(self.cert_path) and os.path.exists(self.key_path):
            return
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        os.makedirs(os.path.dirname(self.cert_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.key_path) or ".", exist_ok=True)

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=valid_days))
            .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(f"urn:diep:opcua:{common_name}")]), critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(self.key_path, "wb") as fh:
            fh.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(self.cert_path, "wb") as fh:
            fh.write(cert.public_bytes(serialization.Encoding.PEM))
        logger.info("generated self-signed connector certificate at %s (CN=%s, valid %dd)", self.cert_path, common_name, valid_days)

    def load(self) -> tuple[bytes, bytes]:
        with open(self.cert_path, "rb") as fh:
            self._cert_pem = fh.read()
        with open(self.key_path, "rb") as fh:
            self._key_pem = fh.read()
        self._cert_mtime = os.path.getmtime(self.cert_path)
        from cryptography import x509
        self._x509_cert = x509.load_pem_x509_certificate(self._cert_pem)
        return self._cert_pem, self._key_pem

    def reload_if_changed(self) -> bool:
        try:
            mtime = os.path.getmtime(self.cert_path)
        except FileNotFoundError:
            return False
        if self._cert_mtime is None or mtime != self._cert_mtime:
            self.load()
            logger.info("connector certificate reloaded (mtime changed) — will take effect on next (re)connect")
            return True
        return False

    def expiry_seconds(self) -> float | None:
        """Seconds until the connector's own client cert expires — feeds the
        opcua_certificate_expiry_seconds metric. None if not loaded yet."""
        if self._x509_cert is None:
            return None
        delta = self._x509_cert.not_valid_after_utc - datetime.now(timezone.utc)
        return delta.total_seconds()

    def is_trusted(self, server_cert_der: bytes) -> bool:
        """Checks a server certificate (DER bytes, as asyncua hands back from
        a secure handshake) against the trust store directory by SHA-256
        fingerprint. An empty/missing trust store trusts nothing — fail
        closed, matching "certificate validation" as a real check rather than
        a no-op."""
        if not self.trust_store_dir or not os.path.isdir(self.trust_store_dir):
            return False
        import hashlib
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding

        fingerprint = hashlib.sha256(server_cert_der).hexdigest()
        for fname in os.listdir(self.trust_store_dir):
            path = os.path.join(self.trust_store_dir, fname)
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
                trusted_der = data if fname.endswith(".der") else x509.load_pem_x509_certificate(data).public_bytes(Encoding.DER)
            except Exception as exc:  # noqa: BLE001 — a malformed trust-store entry must not crash validation
                logger.warning("skipping unreadable trust store entry %s: %s", path, exc)
                continue
            if hashlib.sha256(trusted_der).hexdigest() == fingerprint:
                return True
        return False
