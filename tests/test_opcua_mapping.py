"""Tests for services/opcua/mapping.py — pure stdlib + PyYAML, no asyncua
needed. See services/opcua/VALIDATION.md for the overall test/verification
approach (pytest is not importable in this dev environment — see also
test_mdm_*.py's identical caveat)."""
import pytest

from services.opcua.mapping import MappingError, ServerMapping, SubscriptionMapping, parse_mapping


FLAT_DOC = {
    "subscriptions": [
        {"node": "ns=2;s=Battery.SOC", "measurement": "battery_soc"},
        {"node": "ns=2;s=Solar.Power", "measurement": "solar_kw", "deadband_type": "percent", "deadband_value": 1.0},
    ]
}

MULTI_DOC = {
    "servers": [
        {
            "name": "plant1",
            "endpoint_url": "opc.tcp://plant1:4840/",
            "security_policy": "Basic256Sha256",
            "security_mode": "SignAndEncrypt",
            "subscriptions": [{"node": "ns=2;s=Battery.SOC", "measurement": "battery_soc"}],
        },
        {
            "name": "plant2",
            "endpoint_url": "opc.tcp://plant2:4840/",
            "subscriptions": [{"node": "nsu=urn:x;s=Solar.Power", "measurement": "solar_kw"}],
        },
    ]
}

DEFAULTS = dict(default_endpoint_url="opc.tcp://localhost:4840/", default_security_policy="None", default_security_mode="None")


def test_flat_shape_yields_one_default_server():
    servers = parse_mapping(FLAT_DOC, **DEFAULTS)
    assert len(servers) == 1
    assert servers[0].name == "default"
    assert servers[0].endpoint_url == "opc.tcp://localhost:4840/"
    assert len(servers[0].subscriptions) == 2
    assert servers[0].subscriptions[0].measurement == "battery_soc"


def test_multi_server_shape():
    servers = parse_mapping(MULTI_DOC, **DEFAULTS)
    assert [s.name for s in servers] == ["plant1", "plant2"]
    assert servers[0].security_policy == "Basic256Sha256"
    assert servers[1].security_policy == "None"  # ServerMapping default applied
    assert servers[1].subscriptions[0].node == "nsu=urn:x;s=Solar.Power"


def test_missing_top_level_key_raises():
    with pytest.raises(MappingError):
        parse_mapping({"unrelated": []}, **DEFAULTS)


def test_empty_subscriptions_raises():
    with pytest.raises(MappingError):
        parse_mapping({"subscriptions": []}, **DEFAULTS)


def test_server_with_no_subscriptions_raises():
    doc = {"servers": [{"name": "p1", "endpoint_url": "opc.tcp://p1/", "subscriptions": []}]}
    with pytest.raises(MappingError):
        parse_mapping(doc, **DEFAULTS)


def test_subscription_missing_measurement_raises():
    with pytest.raises(MappingError):
        SubscriptionMapping(node="ns=2;s=X", measurement="")


def test_subscription_bad_deadband_type_raises():
    with pytest.raises(MappingError):
        SubscriptionMapping(node="ns=2;s=X", measurement="x", deadband_type="bogus")


def test_server_missing_endpoint_url_raises():
    with pytest.raises(MappingError):
        ServerMapping(name="p1", endpoint_url="", subscriptions=[SubscriptionMapping(node="ns=2;s=X", measurement="x")])


def test_root_must_be_mapping():
    with pytest.raises(MappingError):
        parse_mapping(["not", "a", "dict"], **DEFAULTS)
