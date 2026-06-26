"""DIEP OPC UA connector — service entrypoint (Phases 1-3).

Wires configuration + mapping + security + per-server connect/subscribe
workers + health/metrics server, with graceful shutdown on SIGTERM/SIGINT.
Per the sprint's explicit scope: no MQTT/Kafka publishing here — each
worker's job ends at handing validated `InternalMeasurement`s to the sink
(see measurement.py); mapping those into the canonical telemetry contract is
the next sprint.
"""
from __future__ import annotations

import asyncio
import logging
import signal

from .client import OpcUaConnection
from .config import Settings
from .health import start_health_server
from .mapping import ServerMapping, load_mapping
from .mdm_consumer import MdmConsumer
from .measurement import MeasurementSink
from .metrics import OpcuaMetrics
from .security import CertificateStore, SecurityConfig
from .subscription import SubscriptionManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("diep-opcua")


def build_security_config(server: ServerMapping) -> SecurityConfig | None:
    if server.security_policy == "None" and not server.username:
        return None
    return SecurityConfig(
        policy=server.security_policy,
        mode=server.security_mode,
        cert_path=Settings.SECURITY_CERT_PATH,
        key_path=Settings.SECURITY_KEY_PATH,
        trust_store_dir=Settings.SECURITY_TRUST_STORE_DIR,
        username=server.username,
        password=server.password,
    )


class ServerWorker:
    """One per configured server: owns the connection + subscription manager
    and the connect/subscribe/reconnect run loop."""

    def __init__(self, server: ServerMapping, security: SecurityConfig | None,
                 cert_store: CertificateStore | None, sink: MeasurementSink, metrics: OpcuaMetrics):
        self.server = server
        self.connection = OpcUaConnection(server, security=security, cert_store=cert_store, metrics=metrics)
        self.subscriptions = SubscriptionManager(self.connection, sink, metrics=metrics)

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.connection.reconnect_with_backoff(stop_event)
            if stop_event.is_set():
                break
            try:
                await self.subscriptions.recover_monitored_items()
            except Exception as exc:  # noqa: BLE001 — subscribe failure should trigger a reconnect, not crash the worker
                logger.warning("%s: failed to establish subscriptions (%s); reconnecting", self.server.name, exc)
                await self.connection.disconnect()
                continue
            self.connection.start_session_renewal_loop()
            await self._wait_until_disconnected_or_stopped(stop_event)
            if not stop_event.is_set():
                logger.warning("%s: connection lost; reconnecting", self.server.name)
        await self.connection.disconnect()

    async def _wait_until_disconnected_or_stopped(self, stop_event: asyncio.Event) -> None:
        while self.connection.connected and not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=Settings.CONNECTION_POLL_INTERVAL_S)
            except asyncio.TimeoutError:
                pass


async def _cert_reload_loop(cert_store: CertificateStore, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=Settings.SECURITY_CERT_RELOAD_INTERVAL_S)
        except asyncio.TimeoutError:
            cert_store.reload_if_changed()


async def async_main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            logger.warning("signal handlers unsupported on this platform; relying on KeyboardInterrupt only")

    servers = load_mapping(
        Settings.MAPPING_FILE,
        default_endpoint_url=Settings.DEFAULT_ENDPOINT_URL,
        default_security_policy=Settings.DEFAULT_SECURITY_POLICY,
        default_security_mode=Settings.DEFAULT_SECURITY_MODE,
    )

    metrics = OpcuaMetrics()
    cert_store = None
    if any(s.security_policy != "None" for s in servers):
        cert_store = CertificateStore(Settings.SECURITY_CERT_PATH, Settings.SECURITY_KEY_PATH, Settings.SECURITY_TRUST_STORE_DIR)
        if Settings.SECURITY_AUTOGENERATE_CERT:
            cert_store.ensure_self_signed_cert()
        cert_store.load()
        metrics.certificate_expiry_seconds.set_function(lambda: cert_store.expiry_seconds() or 0.0)

    sink = MeasurementSink(history_size=Settings.SINK_HISTORY_SIZE, metrics=metrics)
    workers = [ServerWorker(s, build_security_config(s), cert_store, sink, metrics) for s in servers]

    mdm_consumer = None
    if Settings.MDM_CONSUMER_ENABLED:
        mdm_consumer = MdmConsumer(
            sink, broker=Settings.MDM_MQTT_BROKER, port=Settings.MDM_MQTT_PORT,
            topic=Settings.MDM_TRUSTED_TOPIC, tls=Settings.MDM_MQTT_TLS,
            ca_certs=Settings.MDM_MQTT_CA_CERTS, client_cert=Settings.MDM_MQTT_CLIENT_CERT,
            client_key=Settings.MDM_MQTT_CLIENT_KEY, username=Settings.MDM_MQTT_USER,
            password=Settings.MDM_MQTT_PASS,
        )
        mdm_consumer.start()
        logger.info("MDM trusted-stream consumer starting: topic=%s", Settings.MDM_TRUSTED_TOPIC)

    def status_provider() -> dict:
        return {
            "servers": {
                w.server.name: {
                    "connected": w.connection.connected,
                    "endpoint_url": w.server.endpoint_url,
                    "reconnect_count": w.connection.reconnect_count,
                    "monitored_items": w.subscriptions.monitored_item_count,
                }
                for w in workers
            },
            "mdm_consumer_enabled": Settings.MDM_CONSUMER_ENABLED,
            "latest_measurements": sink.latest(),
        }

    start_health_server(Settings.HEALTH_PORT, status_provider=status_provider)
    logger.info("OPC UA connector starting: %d server(s) configured", len(workers))

    cert_reload_task = None
    if cert_store is not None:
        cert_reload_task = asyncio.create_task(_cert_reload_loop(cert_store, stop_event))

    results = await asyncio.gather(*(w.run(stop_event) for w in workers), return_exceptions=True)
    for worker, result in zip(workers, results):
        if isinstance(result, Exception):
            logger.error("%s: worker terminated with an unhandled error: %s", worker.server.name, result)

    if mdm_consumer is not None:
        mdm_consumer.stop()
    if cert_reload_task is not None:
        cert_reload_task.cancel()
    logger.info("OPC UA connector shut down")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
