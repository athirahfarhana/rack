"""
Mock simulator.

While no real Gateway hardware is connected, this plays the role of the
physical Gateway on a timer so the Device Sidebar / Zone Properties panel
show believable "Online" status and heartbeats with zero hardware attached:

  - Publishes a heartbeat over MQTT on a timer, using the exact payload
    shape a real Gateway would (`{prefix}/{gw_id}/tx/heartbeat`). If no
    broker is reachable it falls back to updating the DB directly so the
    UI still reflects Online status with no infrastructure at all.

Unlike the upstream reference project, this build does NOT randomly
generate fake Store/Pick operations - those are entirely user-driven from
the dashboard (Inbound/Outbound panels), matching the original system's
manual workflow. Flip to "live" mode (Settings) and this goes quiet;
only real MQTT traffic drives gateway status from then on.
"""
import datetime as dt
import logging
import random
import threading
import time

from . import models, runtime_state
from .config import settings
from .database import session_scope
from .events import broadcast_threadsafe
from .mqtt_client import mqtt_service

logger = logging.getLogger("smart_warehouse.mock")


class MockEngine:
    def start(self) -> None:
        threading.Thread(target=self._loop, name="mock-engine", daemon=True).start()

    def _loop(self) -> None:
        while True:
            time.sleep(settings.MOCK_TICK_SEC)
            if runtime_state.get_mode() != "mock":
                continue
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("Mock engine tick failed")

    def _tick(self) -> None:
        with session_scope() as db:
            gateways = db.query(models.Gateway).filter(models.Gateway.is_simulated.is_(True)).all()
            for gw in gateways:
                self._simulate_heartbeat(db, gw)

    def _simulate_heartbeat(self, db, gw: models.Gateway) -> None:
        if random.random() < settings.MOCK_FLAKY_DEVICE_CHANCE:
            return  # simulate a missed heartbeat now and then

        modules = db.query(models.ZoneModule).filter(models.ZoneModule.gateway_id == gw.id).all()
        payload = {
            "event": "heartbeat",
            "gateway_id": gw.gw_id,
            "status": "online",
            "active_nodes_count": len(modules),
            "wifi_rssi": random.randint(-70, -35),
            "uptime_seconds": (gw.uptime_sec or 0) + int(settings.MOCK_TICK_SEC),
            "simulated": True,
        }

        if mqtt_service.connected:
            mqtt_service.publish(f"{settings.MQTT_TOPIC_PREFIX}/{gw.gw_id}/tx/heartbeat", payload, gw_id=gw.gw_id)
        else:
            now = dt.datetime.now(dt.timezone.utc)
            gw.status = "Online"
            gw.last_heartbeat = now
            gw.wifi_rssi = payload["wifi_rssi"]
            gw.uptime_sec = payload["uptime_seconds"]
            gw.active_nodes_count = len(modules)
            for m in modules:
                m.status = "Online"
                m.last_seen = now
            db.commit()
            broadcast_threadsafe(
                {
                    "type": "gateway_heartbeat",
                    "gatewayId": gw.id,
                    "gwId": gw.gw_id,
                    "status": "Online",
                    "wifiRssi": gw.wifi_rssi,
                }
            )


mock_engine = MockEngine()
