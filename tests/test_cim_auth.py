"""services/cim/auth.py -- Bearer token resolves to the correct tenant_id;
a missing/unknown token is rejected. This is the security-critical module:
a bug here would leak one tenant's data to another's token."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import auth  # noqa: E402
from services.cim.config import Settings  # noqa: E402


class _FakeRequest:
    def __init__(self, header_value: str | None):
        self.headers = {"authorization": header_value} if header_value is not None else {}


def _with_api_keys(raw: str):
    orig = Settings.CIM_API_KEYS_RAW
    Settings.CIM_API_KEYS_RAW = raw

    def restore():
        Settings.CIM_API_KEYS_RAW = orig
    return restore


def test_known_tenant_scoped_token_resolves_to_its_tenant():
    restore = _with_api_keys("tok-a=tenant-a,tok-b=tenant-b")
    try:
        principal = auth._principal_from_request(_FakeRequest("Bearer tok-a"))
    finally:
        restore()
    assert principal is not None
    assert principal.tenant_id == "tenant-a"


def test_different_tokens_resolve_to_different_tenants_no_cross_talk():
    restore = _with_api_keys("tok-a=tenant-a,tok-b=tenant-b")
    try:
        principal_a = auth._principal_from_request(_FakeRequest("Bearer tok-a"))
        principal_b = auth._principal_from_request(_FakeRequest("Bearer tok-b"))
    finally:
        restore()
    assert principal_a.tenant_id == "tenant-a"
    assert principal_b.tenant_id == "tenant-b"
    assert principal_a.tenant_id != principal_b.tenant_id


def test_empty_tenant_after_equals_means_unscoped_none():
    restore = _with_api_keys("svc-token=")
    try:
        principal = auth._principal_from_request(_FakeRequest("Bearer svc-token"))
    finally:
        restore()
    assert principal is not None
    assert principal.tenant_id is None


def test_unknown_token_resolves_to_no_principal():
    restore = _with_api_keys("tok-a=tenant-a")
    try:
        principal = auth._principal_from_request(_FakeRequest("Bearer totally-bogus"))
    finally:
        restore()
    assert principal is None


def test_missing_authorization_header_resolves_to_no_principal():
    restore = _with_api_keys("tok-a=tenant-a")
    try:
        principal = auth._principal_from_request(_FakeRequest(None))
    finally:
        restore()
    assert principal is None


def test_non_bearer_authorization_scheme_is_rejected():
    restore = _with_api_keys("tok-a=tenant-a")
    try:
        principal = auth._principal_from_request(_FakeRequest("Basic dXNlcjpwYXNz"))
    finally:
        restore()
    assert principal is None


def test_require_principal_raises_401_for_no_principal():
    restore = _with_api_keys("tok-a=tenant-a")
    try:
        raised_status = None
        try:
            auth.require_principal(_FakeRequest(None))
        except Exception as exc:  # fastapi.HTTPException
            raised_status = getattr(exc, "status_code", None)
    finally:
        restore()
    assert raised_status == 401


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
