"""OPC UA connector configuration — stdlib only, no third-party imports (so
importing this module never fails regardless of what's installed).

Per the sprint brief, node definitions come from the declarative mapping file
(`mapping.py`), not from here — this module only holds the connector's own
runtime knobs (timeouts, ports, reconnect/security paths).
"""
from __future__ import annotations

import os


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # Declarative node mapping — see mapping.py for the file format. Supports
    # both the single-server flat shape (top-level `subscriptions:`) and the
    # multi-server shape (top-level `servers:`).
    MAPPING_FILE = os.getenv("OPCUA_MAPPING_FILE", "services/opcua/config/mapping.example.yaml")

    # Used only by the single-server flat mapping shape, where the file itself
    # carries no endpoint_url (matches the sprint's literal example, which has
    # no `servers:` wrapper at all).
    DEFAULT_ENDPOINT_URL = os.getenv("OPCUA_SERVER_URL", "opc.tcp://localhost:4840/freeopcua/server/")
    DEFAULT_SECURITY_POLICY = os.getenv("OPCUA_SECURITY_POLICY", "None")
    DEFAULT_SECURITY_MODE = os.getenv("OPCUA_SECURITY_MODE", "None")

    HEALTH_PORT = int(os.getenv("OPCUA_HEALTH_PORT", "9202"))

    # Reconnect backoff (applies per server connection)
    RECONNECT_INITIAL_DELAY_S = float(os.getenv("OPCUA_RECONNECT_INITIAL_DELAY_S", "2"))
    RECONNECT_MAX_DELAY_S = float(os.getenv("OPCUA_RECONNECT_MAX_DELAY_S", "60"))
    RECONNECT_BACKOFF_FACTOR = float(os.getenv("OPCUA_RECONNECT_BACKOFF_FACTOR", "1.5"))

    # Session: requested timeout vs. what the server actually grants can
    # differ (Phase 0 discovery: the asyncua reference server capped a
    # 3,600,000 ms request down to 600,000 ms) — renewal is scheduled off the
    # granted value, with a safety margin subtracted.
    REQUESTED_SESSION_TIMEOUT_MS = int(os.getenv("OPCUA_SESSION_TIMEOUT_MS", "3600000"))
    SESSION_RENEWAL_MARGIN_S = float(os.getenv("OPCUA_SESSION_RENEWAL_MARGIN_S", "60"))

    # Browse cache
    BROWSE_CACHE_TTL_S = float(os.getenv("OPCUA_BROWSE_CACHE_TTL_S", "300"))

    # How often the run loop polls connection.connected for an unexpected
    # drop (session renewal failure sets it False — see client.py) while
    # otherwise idle between stop-event checks.
    CONNECTION_POLL_INTERVAL_S = float(os.getenv("OPCUA_CONNECTION_POLL_INTERVAL_S", "5"))

    # Security (Phase 3) — file paths for the connector's own client identity
    # and the directory of trusted server certificates. Generated on first run
    # if SECURITY_AUTOGENERATE_CERT is left on and no cert exists yet.
    SECURITY_CERT_PATH = os.getenv("OPCUA_CERT_PATH", "services/opcua/security/certs/connector-cert.pem")
    SECURITY_KEY_PATH = os.getenv("OPCUA_KEY_PATH", "services/opcua/security/certs/connector-key.pem")
    SECURITY_TRUST_STORE_DIR = os.getenv("OPCUA_TRUST_STORE_DIR", "services/opcua/security/trusted")
    SECURITY_AUTOGENERATE_CERT = _bool("OPCUA_SECURITY_AUTOGENERATE_CERT", True)
    SECURITY_CERT_RELOAD_INTERVAL_S = float(os.getenv("OPCUA_CERT_RELOAD_INTERVAL_S", "300"))

    # In-memory sink: how many recent measurements per (server, measurement)
    # are retained for /health introspection (see measurement.py).
    SINK_HISTORY_SIZE = int(os.getenv("OPCUA_SINK_HISTORY_SIZE", "50"))

    # Post-SIT stabilization sprint, Work Item 5 -- consumes MDM's "trusted"
    # MQTT stream (see mdm_consumer.py). Same broker/identity-reuse pattern
    # as services/mdm and the ingestor: this connector authenticates as the
    # "ingestor" mTLS identity too (see mosquitto/config/acl's readwrite
    # grant on diep/+/+/trusted, added this sprint).
    MDM_CONSUMER_ENABLED = _bool("OPCUA_MDM_CONSUMER_ENABLED", True)
    MDM_MQTT_BROKER = os.getenv("MQTT_BROKER", "diep-mqtt")
    MDM_MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
    MDM_MQTT_TLS = _bool("MQTT_TLS", True)
    MDM_MQTT_CA_CERTS = os.getenv("MQTT_CA_CERTS", "/certs/ca.crt")
    MDM_MQTT_CLIENT_CERT = os.getenv("MQTT_CLIENT_CERT", "/certs/ingestor.crt")
    MDM_MQTT_CLIENT_KEY = os.getenv("MQTT_CLIENT_KEY", "/certs/ingestor.key")
    MDM_MQTT_USER = os.getenv("MQTT_USER", "")
    MDM_MQTT_PASS = os.getenv("MQTT_PASS", "")
    MDM_TRUSTED_TOPIC = os.getenv("OPCUA_MDM_TRUSTED_TOPIC", "diep/+/+/trusted")
