"""Tests for services/opcua/security.py. The certificate/trust-store logic
uses the real `cryptography` library (it is actually installed in this
environment) — these are genuine, not faked, assertions. Only
`build_security_string()`'s consumption by asyncua is unverified — see
VALIDATION.md."""
import os

import pytest

from services.opcua.security import CertificateStore, SecurityConfig, SecurityError, build_security_string


def test_none_policy_is_valid_with_no_certs():
    sec = SecurityConfig(policy="None", mode="None")
    assert build_security_string(sec) is None


def test_secure_policy_requires_certs():
    with pytest.raises(SecurityError):
        SecurityConfig(policy="Basic256Sha256", mode="SignAndEncrypt")


def test_secure_policy_requires_non_none_mode():
    with pytest.raises(SecurityError):
        SecurityConfig(policy="Basic256Sha256", mode="None", cert_path="c", key_path="k")


def test_unsupported_policy_rejected():
    with pytest.raises(SecurityError):
        SecurityConfig(policy="Aes256Sha256RsaPss", mode="Sign", cert_path="c", key_path="k")


def test_build_security_string_shape():
    sec = SecurityConfig(policy="Basic256Sha256", mode="SignAndEncrypt", cert_path="/c.pem", key_path="/k.pem")
    s = build_security_string(sec)
    assert s == "Basic256Sha256,SignAndEncrypt,/c.pem,/k.pem"


def test_certificate_store_generates_and_loads_real_cert(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    store = CertificateStore(cert_path, key_path)
    store.ensure_self_signed_cert(common_name="test-connector", valid_days=30)
    assert os.path.exists(cert_path) and os.path.exists(key_path)

    cert_pem, key_pem = store.load()
    assert b"BEGIN CERTIFICATE" in cert_pem
    assert b"PRIVATE KEY" in key_pem

    expiry = store.expiry_seconds()
    assert expiry is not None
    assert 29 * 86400 < expiry < 31 * 86400


def test_certificate_store_does_not_regenerate_existing_cert(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    store = CertificateStore(cert_path, key_path)
    store.ensure_self_signed_cert()
    first_bytes = open(cert_path, "rb").read()
    store.ensure_self_signed_cert()
    assert open(cert_path, "rb").read() == first_bytes


def test_reload_if_changed_detects_mtime_change(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    store = CertificateStore(cert_path, key_path)
    store.ensure_self_signed_cert()
    store.load()
    assert store.reload_if_changed() is False  # unchanged since load()

    import time
    time.sleep(0.01)
    os.utime(cert_path, None)  # bump mtime without changing content
    assert store.reload_if_changed() is True


def test_is_trusted_with_matching_cert_in_store(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    trust_dir = tmp_path / "trusted"
    trust_dir.mkdir()

    store = CertificateStore(cert_path, key_path, trust_store_dir=str(trust_dir))
    store.ensure_self_signed_cert()
    cert_pem, _ = store.load()

    # Simulate "the server's certificate" being copied into the trust store —
    # here it's the same cert, which is the realistic case for a self-signed
    # mutual-trust setup in a lab/test environment.
    (trust_dir / "server.pem").write_bytes(cert_pem)

    server_cert_der = x509.load_pem_x509_certificate(cert_pem).public_bytes(Encoding.DER)
    assert store.is_trusted(server_cert_der) is True


def test_is_trusted_false_for_unknown_cert(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    store = CertificateStore(cert_path, key_path, trust_store_dir=str(tmp_path / "trusted"))
    assert store.is_trusted(b"not-a-real-cert") is False  # missing trust store dir -> fail closed
