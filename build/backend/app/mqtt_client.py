"""
MQTT bridge between Rack Gateways (real or simulated) and the backend.

Topic structure (hierarchical, keyed by the Gateway's own id - individual
Zone Modules have no WiFi/MQTT of their own; the Gateway bridges its wired
RS485 daisy-chain of cubbies into MQTT):

  Publish (Gateway -> Backend):   warehouse/racks/{gw_id}/tx/...
  Subscribe (Backend -> Gateway): warehouse/racks/{gw_id}/rx/...

tx leaves we subscribe to:
  tx/heartbeat   {event, gateway_id, status, active_nodes_count, wifi_rssi, uptime_seconds}
  tx/discovery   {event: node_discovered, gateway_id, node_uuid, hardware_rev, capabilities, timestamp}
  tx/topology    {event: topology_report, gateway_id, total_nodes_detected, nodes: [...]}
  tx/button      {event: button_press, gateway_id, node_uuid, button, action, timestamp}

rx leaves we publish:
  rx/led         {command: set_led, node_uuid, state, color_hex, effect, timeout_ms}
  rx/ping        {} - optional convenience extension (not in the base spec):
                 asks the gateway to send a heartbeat immediately. Real
                 firmware that doesn't implement this can safely ignore it;
                 the UI just waits for the next natural heartbeat either way.

A background watchdog flips a Gateway (and everything wired to it) Offline
if its heartbeat goes stale, independent of what it last claimed.

Every processed message (in and out) is written to MqttPayloadLog so
Settings -> Devices can show "what did the hardware actually send" for
debugging - pruned to the last MAX_LOG_PER_GATEWAY entries per gateway.

This module intentionally degrades gracefully: if no broker is reachable,
the backend logs a warning and keeps serving the REST API normally.
"""
import datetime as dt
import json
import logging
import threading
import time

import paho.mqtt.client as mqtt

from . import models, services
from .config import settings
from .database import session_scope
from .events import broadcast_threadsafe

logger = logging.getLogger("smart_warehouse.mqtt")

MAX_LOG_PER_GATEWAY = 100
DEFAULT_LED_TIMEOUT_MS = 30000


class MqttService:
    def __init__(self) -> None:
        self.client: mqtt.Client | None = None
        self.connected = False

    # ---------------------------------------------------------------- setup
    def start(self) -> None:
        if not settings.MQTT_ENABLED:
            logger.warning("MQTT disabled via MQTT_ENABLED=false. Heartbeats/LEDs will not flow.")
            return

        client = mqtt.Client(client_id=settings.MQTT_CLIENT_ID, clean_session=True)
        if settings.MQTT_USERNAME:
            client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self.client = client

        def _connect_loop():
            while True:
                try:
                    client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=30)
                    client.loop_forever(retry_first_connection=True)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("MQTT connect failed (%s). Retrying in 5s...", exc)
                    time.sleep(5)

        threading.Thread(target=_connect_loop, name="mqtt-client", daemon=True).start()
        threading.Thread(target=self._offline_watchdog, name="mqtt-watchdog", daemon=True).start()

    # ------------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            prefix = settings.MQTT_TOPIC_PREFIX
            client.subscribe(f"{prefix}/+/tx/heartbeat")
            client.subscribe(f"{prefix}/+/tx/discovery")
            client.subscribe(f"{prefix}/+/tx/topology")
            client.subscribe(f"{prefix}/+/tx/button")
            logger.info("MQTT connected to %s:%s", settings.MQTT_HOST, settings.MQTT_PORT)
            broadcast_threadsafe({"type": "mqtt_status", "connected": True})
        else:
            logger.warning("MQTT connect returned rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning("MQTT disconnected (rc=%s)", rc)
        broadcast_threadsafe({"type": "mqtt_status", "connected": False})

    def _on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split("/")
            # warehouse/racks/{gw_id}/tx/{leaf}
            gw_id = parts[-3]
            leaf = parts[-1]
            raw = msg.payload.decode("utf-8") or "{}"
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to parse MQTT message on %s", msg.topic)
            return

        self._log_payload(gw_id, "in", msg.topic, raw)

        if leaf == "heartbeat":
            self._handle_heartbeat(gw_id, payload)
        elif leaf == "discovery":
            self._handle_discovery(gw_id, payload)
        elif leaf == "topology":
            self._handle_topology(gw_id, payload)
        elif leaf == "button":
            self._handle_button(gw_id, payload)

    # ------------------------------------------------------------- handlers
    def _get_or_create_gateway(self, db, gw_id: str, is_simulated: bool = False) -> models.Gateway:
        gw = db.query(models.Gateway).filter(models.Gateway.gw_id == gw_id).first()
        if not gw:
            gw = models.Gateway(gw_id=gw_id, is_simulated=is_simulated)
            db.add(gw)
            db.flush()
        return gw

    def _handle_heartbeat(self, gw_id: str, payload: dict) -> None:
        with session_scope() as db:
            gw = self._get_or_create_gateway(db, gw_id, is_simulated=bool(payload.get("simulated", False)))
            now = dt.datetime.now(dt.timezone.utc)
            gw.status = "Online" if payload.get("status", "online") == "online" else "Offline"
            gw.last_heartbeat = now
            gw.wifi_rssi = payload.get("wifi_rssi")
            gw.uptime_sec = payload.get("uptime_seconds")
            gw.active_nodes_count = payload.get("active_nodes_count")

            # A gateway heartbeat implicitly means its attached zone modules
            # are alive too (mirrors the offline watchdog below, which
            # cascades Offline the same way) - without this, modules only
            # ever go Offline and never recover once the gateway itself
            # comes back, since nothing else refreshes their last_seen.
            for module in gw.zone_modules:
                module.status = gw.status
                module.last_seen = now

            db.add(
                models.HeartbeatEvent(
                    gateway_id=gw.id,
                    wifi_rssi=gw.wifi_rssi,
                    uptime_sec=gw.uptime_sec,
                    active_nodes_count=gw.active_nodes_count,
                )
            )
            db.commit()

            broadcast_threadsafe(
                {
                    "type": "gateway_heartbeat",
                    "gatewayId": gw.id,
                    "gwId": gw_id,
                    "status": gw.status,
                    "wifiRssi": gw.wifi_rssi,
                    "activeNodesCount": gw.active_nodes_count,
                }
            )

    def _handle_discovery(self, gw_id: str, payload: dict) -> None:
        node_uuid = payload.get("node_uuid")
        if not node_uuid:
            return
        with session_scope() as db:
            gw = self._get_or_create_gateway(db, gw_id)
            module = db.query(models.ZoneModule).filter(models.ZoneModule.node_uuid == node_uuid).first()
            is_new = False
            if not module:
                module = models.ZoneModule(node_uuid=node_uuid, gateway_id=gw.id, is_simulated=gw.is_simulated)
                db.add(module)
                is_new = True
            module.gateway_id = gw.id
            module.hardware_rev = payload.get("hardware_rev", module.hardware_rev)
            caps = payload.get("capabilities")
            if caps:
                module.capabilities = ",".join(caps) if isinstance(caps, list) else str(caps)
            module.status = "Online"
            module.last_seen = dt.datetime.now(dt.timezone.utc)
            db.commit()

            broadcast_threadsafe(
                {"type": "node_discovered", "nodeUuid": node_uuid, "gwId": gw_id, "isNew": is_new}
            )

    def _handle_topology(self, gw_id: str, payload: dict) -> None:
        nodes = payload.get("nodes", [])
        with session_scope() as db:
            gw = self._get_or_create_gateway(db, gw_id)
            gw.active_nodes_count = payload.get("total_nodes_detected", len(nodes))
            now = dt.datetime.now(dt.timezone.utc)

            for node in nodes:
                node_uuid = node.get("node_uuid")
                if not node_uuid:
                    continue
                module = db.query(models.ZoneModule).filter(models.ZoneModule.node_uuid == node_uuid).first()
                if not module:
                    module = models.ZoneModule(node_uuid=node_uuid, gateway_id=gw.id, is_simulated=gw.is_simulated)
                    db.add(module)
                module.gateway_id = gw.id
                module.daisy_chain_index = node.get("daisy_chain_index", module.daisy_chain_index)
                module.firmware_version = node.get("firmware_ver", module.firmware_version)
                module.status = "Online" if node.get("status", "online") == "online" else "Offline"
                module.last_seen = now

            db.commit()
            broadcast_threadsafe({"type": "topology_report", "gwId": gw_id, "nodeCount": len(nodes)})

    def _handle_button(self, gw_id: str, payload: dict) -> None:
        node_uuid = payload.get("node_uuid")
        button = payload.get("button")
        if not node_uuid or not button:
            return

        with session_scope() as db:
            module = db.query(models.ZoneModule).filter(models.ZoneModule.node_uuid == node_uuid).first()
            if not module or not module.zone_id:
                logger.info("Button press on unassigned node %s - ignored", node_uuid)
                return

            gw = db.query(models.Gateway).filter(models.Gateway.id == module.gateway_id).first()
            result = services.resolve_button_press(
                db, module.zone_id, button, is_simulated=bool(gw.is_simulated if gw else False)
            )
            broadcast_threadsafe(
                {"type": "button_press", "nodeUuid": node_uuid, "zoneId": module.zone_id, "button": button, **result}
            )
            if result.get("resolved"):
                self.publish_led_off_for_node(node_uuid)

    # -------------------------------------------------------------- publish
    def _log_payload(self, gw_id: str, direction: str, topic: str, raw_payload: str) -> None:
        try:
            with session_scope() as db:
                db.add(models.MqttPayloadLog(gw_id=gw_id, direction=direction, topic=topic, payload=raw_payload))
                db.commit()
                # Prune old entries beyond MAX_LOG_PER_GATEWAY for this gateway.
                excess = (
                    db.query(models.MqttPayloadLog)
                    .filter(models.MqttPayloadLog.gw_id == gw_id)
                    .order_by(models.MqttPayloadLog.timestamp.desc())
                    .offset(MAX_LOG_PER_GATEWAY)
                    .all()
                )
                for row in excess:
                    db.delete(row)
                if excess:
                    db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to log MQTT payload for %s", gw_id)

    def publish(self, topic: str, payload: dict, gw_id: str | None = None) -> None:
        raw = json.dumps(payload)
        if gw_id:
            self._log_payload(gw_id, "out", topic, raw)
        if not self.client or not self.connected:
            return
        self.client.publish(topic, raw, qos=0)

    def publish_led(self, gw_id: str, node_uuid: str, color_hex: str, state: str = "ON", effect: str = "solid", timeout_ms: int = DEFAULT_LED_TIMEOUT_MS) -> None:
        self.publish(
            f"{settings.MQTT_TOPIC_PREFIX}/{gw_id}/rx/led",
            {
                "command": "set_led",
                "node_uuid": node_uuid,
                "state": state,
                "color_hex": color_hex,
                "effect": effect,
                "timeout_ms": timeout_ms,
            },
            gw_id=gw_id,
        )

    def publish_led_for_zone(self, db, zone_id: str, color_hex: str, state: str = "ON", effect: str = "solid") -> None:
        zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
        module = zone.zone_module if zone else None
        if module and module.gateway:
            self.publish_led(module.gateway.gw_id, module.node_uuid, color_hex, state, effect)

    def publish_led_off_for_node(self, node_uuid: str) -> None:
        with session_scope() as db:
            module = db.query(models.ZoneModule).filter(models.ZoneModule.node_uuid == node_uuid).first()
            if module and module.gateway:
                self.publish_led(module.gateway.gw_id, node_uuid, "#000000", "OFF")

    def publish_identify(self, gw_id: str, node_uuid: str) -> None:
        """No dedicated 'identify' leaf in the base protocol - reuse set_led
        with a blink effect, which is what the physical LED is for anyway."""
        self.publish_led(gw_id, node_uuid, "#FFFFFF", "ON", effect="blink", timeout_ms=5000)

    def publish_ping(self, gw_id: str) -> None:
        """Optional convenience extension, not in the base spec. Real
        firmware that doesn't implement rx/ping can safely ignore it - the
        UI just falls back to waiting for the next natural heartbeat."""
        self.publish(f"{settings.MQTT_TOPIC_PREFIX}/{gw_id}/rx/ping", {"ts": time.time()}, gw_id=gw_id)

    # -------------------------------------------------------------- watchdog
    def _offline_watchdog(self) -> None:
        while True:
            time.sleep(settings.HEARTBEAT_WATCHDOG_TICK_SEC)
            try:
                with session_scope() as db:
                    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
                        seconds=settings.HEARTBEAT_OFFLINE_TIMEOUT_SEC
                    )
                    stale = (
                        db.query(models.Gateway)
                        .filter(models.Gateway.status == "Online")
                        .filter((models.Gateway.last_heartbeat.is_(None)) | (models.Gateway.last_heartbeat < cutoff))
                        .all()
                    )
                    for gw in stale:
                        gw.status = "Offline"
                        for module in gw.zone_modules:
                            module.status = "Offline"
                        broadcast_threadsafe({"type": "gateway_heartbeat", "gatewayId": gw.id, "gwId": gw.gw_id, "status": "Offline"})
                    if stale:
                        db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Offline watchdog tick failed")


mqtt_service = MqttService()
