"""Declarative OPC UA node mapping — "node definitions must come from
configuration rather than source code" (Phase 2 deliverable).

Two YAML shapes are supported, both loaded into the same `ServerMapping` /
`SubscriptionMapping` dataclasses:

1. Single-server flat shape (matches the sprint brief's literal example —
   no `servers:` wrapper at all; the endpoint/security come from
   `config.Settings.DEFAULT_*`):

       subscriptions:
         - node: ns=2;s=Battery.SOC
           measurement: battery_soc

2. Multi-server shape, for "one or more OPC UA servers" (success criteria):

       servers:
         - name: plant1
           endpoint_url: "opc.tcp://plant1:4840/"
           security_policy: Basic256Sha256
           security_mode: SignAndEncrypt
           subscriptions:
             - node: ns=2;s=Battery.SOC
               measurement: battery_soc

PyYAML only — no asyncua/cryptography import here, so a config-loading test
doesn't need either installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class MappingError(ValueError):
    pass


@dataclass
class SubscriptionMapping:
    node: str
    measurement: str
    sampling_interval_ms: float = 1000.0
    deadband_type: str = "none"  # "none" | "absolute" | "percent"
    deadband_value: float = 0.0
    queue_size: int = 10

    def __post_init__(self):
        if not self.node or not isinstance(self.node, str):
            raise MappingError("subscription entry missing required string field 'node'")
        if not self.measurement or not isinstance(self.measurement, str):
            raise MappingError(f"subscription entry for node {self.node!r} missing required field 'measurement'")
        if self.deadband_type not in ("none", "absolute", "percent"):
            raise MappingError(f"node {self.node!r}: invalid deadband_type {self.deadband_type!r}")
        if self.sampling_interval_ms <= 0:
            raise MappingError(f"node {self.node!r}: sampling_interval_ms must be > 0")
        if self.queue_size < 0:
            raise MappingError(f"node {self.node!r}: queue_size must be >= 0")


@dataclass
class ServerMapping:
    name: str
    endpoint_url: str
    security_policy: str = "None"
    security_mode: str = "None"
    username: str | None = None
    password: str | None = None
    subscriptions: list[SubscriptionMapping] = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            raise MappingError("server entry missing required field 'name'")
        if not self.endpoint_url:
            raise MappingError(f"server {self.name!r} missing required field 'endpoint_url'")
        if not self.subscriptions:
            raise MappingError(f"server {self.name!r} has no subscriptions configured")


def _build_subscriptions(raw_list) -> list[SubscriptionMapping]:
    if not isinstance(raw_list, list) or not raw_list:
        raise MappingError("'subscriptions' must be a non-empty list")
    return [SubscriptionMapping(**entry) for entry in raw_list]


def parse_mapping(doc: dict, *, default_endpoint_url: str, default_security_policy: str,
                   default_security_mode: str) -> list[ServerMapping]:
    """Pure function over an already-parsed YAML dict — kept separate from
    file I/O so tests can exercise both mapping shapes without touching disk."""
    if not isinstance(doc, dict):
        raise MappingError("mapping file root must be a YAML mapping")

    if "servers" in doc:
        servers_raw = doc["servers"]
        if not isinstance(servers_raw, list) or not servers_raw:
            raise MappingError("'servers' must be a non-empty list")
        servers = []
        for entry in servers_raw:
            entry = dict(entry)
            subs = _build_subscriptions(entry.pop("subscriptions", None))
            servers.append(ServerMapping(subscriptions=subs, **entry))
        return servers

    if "subscriptions" in doc:
        subs = _build_subscriptions(doc["subscriptions"])
        return [ServerMapping(
            name="default",
            endpoint_url=default_endpoint_url,
            security_policy=default_security_policy,
            security_mode=default_security_mode,
            subscriptions=subs,
        )]

    raise MappingError("mapping file must define either 'servers' or 'subscriptions' at the top level")


def load_mapping(path: str, *, default_endpoint_url: str, default_security_policy: str,
                  default_security_mode: str) -> list[ServerMapping]:
    import yaml  # local import: keeps this module loadable for parse_mapping()-only tests

    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return parse_mapping(
        doc,
        default_endpoint_url=default_endpoint_url,
        default_security_policy=default_security_policy,
        default_security_mode=default_security_mode,
    )
