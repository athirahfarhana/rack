"""
Seeds the starter layout to match the existing UST Smart Warehouse Digital
Twin deployment: one rack (RACK A1) with 6 zones (zone-0..zone-5), one
Gateway bridging the rack's MAC-addressed zone modules, and the same
device roster the physical floor already has plugged in. Only runs if the
DB is empty, so it never clobbers real data on restart.
"""
import logging

from . import models
from .database import SessionLocal

logger = logging.getLogger("smart_warehouse.seed")


def run() -> None:
    db = SessionLocal()
    try:
        if db.query(models.Rack).count() > 0:
            return  # already seeded

        logger.info("Seeding UST Smart Warehouse starter layout...")

        rack = models.Rack(id="rack-a1", name="RACK A1", rows=3, cols=3, x=0, y=0, rotation=0)
        db.add(rack)

        zones = [
            models.Zone(id="zone-3", rack_id="rack-a1", name="Zone 3", zone_group="Zone A", x=0, y=0, w=1, h=1),
            models.Zone(id="zone-4", rack_id="rack-a1", name="Zone 4", zone_group="Zone A", x=1, y=0, w=1, h=1),
            models.Zone(id="zone-5", rack_id="rack-a1", name="Zone 5", zone_group="Zone A", x=2, y=0, w=1, h=1),
            models.Zone(
                id="zone-1", rack_id="rack-a1", name="Rack A - Middle Left", zone_group="Zone A", x=0, y=1, w=2, h=1,
                default_led="blue",
            ),
            models.Zone(id="zone-2", rack_id="rack-a1", name="Zone 2", zone_group="Zone A", x=2, y=1, w=1, h=1),
            models.Zone(id="zone-0", rack_id="rack-a1", name="Zone 0", zone_group="Zone A", x=0, y=2, w=3, h=1),
        ]
        db.add_all(zones)

        # The single Master Gateway bridging RACK A1's wired modules to MQTT.
        gateway = models.Gateway(id="gw-rack-a1", gw_id="GW-RACK-A1", rack_id="rack-a1", is_simulated=True)
        db.add(gateway)
        db.flush()

        modules = [
            # Already installed + assigned to zone-1, matching the live floor.
            models.ZoneModule(
                id="zm-f6g7h8", node_uuid="F6:G7:H8:19:J0", gateway_id=gateway.id, zone_id="zone-1",
                module_type="Medium Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
            # Unassigned pool - plugged in, discovered, awaiting zone assignment.
            models.ZoneModule(
                id="zm-k1l2m3", node_uuid="K1:L2:M3:N4:O5", gateway_id=gateway.id,
                module_type="Medium Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
            models.ZoneModule(
                id="zm-aabb01", node_uuid="AA:BB:CC:DD:EE:01", gateway_id=gateway.id,
                module_type="Large Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
            models.ZoneModule(
                id="zm-aabb02", node_uuid="AA:BB:CC:DD:EE:02", gateway_id=gateway.id,
                module_type="Small Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
            models.ZoneModule(
                id="zm-aabb03", node_uuid="AA:BB:CC:DD:EE:03", gateway_id=gateway.id,
                module_type="Medium Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
            models.ZoneModule(
                id="zm-112233", node_uuid="11:22:33:44:55:66", gateway_id=gateway.id,
                module_type="Small Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
            models.ZoneModule(
                id="zm-ccddee", node_uuid="CC:DD:EE:FF:00:11", gateway_id=gateway.id,
                module_type="Large Module", hardware_rev="1.0", capabilities="led_rgb", status="Online",
                is_simulated=True,
            ),
        ]
        db.add_all(modules)

        worker = models.Worker(id="w1", name="Floor Worker", color_hex="#10B981")
        db.add(worker)

        db.commit()
        logger.info("Seed complete: 1 rack, 6 zones, 1 gateway, 7 zone modules.")
    finally:
        db.close()
