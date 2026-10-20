import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from .database import Base


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Rack(Base):
    __tablename__ = "racks"

    id = Column(String, primary_key=True, default=_uid)
    name = Column(String, nullable=False)
    rows = Column(Integer, nullable=False, default=4)
    cols = Column(Integer, nullable=False, default=6)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    rotation = Column(Integer, default=0)  # 0/90/180/270

    zones = relationship("Zone", back_populates="rack", cascade="all, delete-orphan")
    gateway = relationship("Gateway", back_populates="rack", uselist=False)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String, primary_key=True)  # human readable, e.g. "zone-1"
    rack_id = Column(String, ForeignKey("racks.id"), nullable=False)
    name = Column(String, nullable=False)
    zone_group = Column(String, nullable=True)  # "Zone / Shelf Group", e.g. "Zone A"
    x = Column(Integer, nullable=False, default=0)
    y = Column(Integer, nullable=False, default=0)
    w = Column(Integer, nullable=False, default=1)
    h = Column(Integer, nullable=False, default=1)
    barcode = Column(String, nullable=True)  # set (even to "") => QR/barcode zone
    default_led = Column(String, default="blue")
    max_boxes = Column(Integer, default=20)

    rack = relationship("Rack", back_populates="zones")
    zone_module = relationship("ZoneModule", back_populates="zone", uselist=False)


class Gateway(Base):
    """
    The Master Gateway: the only WiFi/MQTT-speaking device on a rack. It
    multiplexes/bridges the wired (RS485) Zone Modules daisy-chained to it
    into structured MQTT JSON, and is what the backend actually talks to.

    Identified by gw_id (e.g. "GW-8A4B2C"), not a MAC on the zone level -
    individual cubbies have no WiFi chip of their own.
    """

    __tablename__ = "gateways"

    id = Column(String, primary_key=True, default=_uid)
    gw_id = Column(String, unique=True, nullable=False)  # e.g. "GW-8A4B2C"
    rack_id = Column(String, ForeignKey("racks.id"), nullable=True)

    status = Column(String, default="Offline")  # Online | Offline (derived from heartbeats)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    wifi_rssi = Column(Integer, nullable=True)
    uptime_sec = Column(Integer, nullable=True)
    active_nodes_count = Column(Integer, nullable=True)
    is_simulated = Column(Boolean, default=False)

    rack = relationship("Rack", back_populates="gateway")
    zone_modules = relationship("ZoneModule", back_populates="gateway", cascade="all, delete-orphan")


class ZoneModule(Base):
    """
    An individual Smart Cubby (Zone Module). No WiFi of its own - it talks
    RS485 to its parent Gateway, which is the thing that actually shows up
    on MQTT. Discovered automatically (single `node_discovered` events, or
    in bulk via a `topology_report`) when physically plugged into the
    daisy-chain.
    """

    __tablename__ = "zone_modules"

    id = Column(String, primary_key=True, default=_uid)
    node_uuid = Column(String, unique=True, nullable=False)  # e.g. "ZMOD-4491-B7"
    gateway_id = Column(String, ForeignKey("gateways.id"), nullable=False)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)

    daisy_chain_index = Column(Integer, nullable=True)
    module_type = Column(String, default="Medium Module")  # Small | Medium | Large Module
    hardware_rev = Column(String, nullable=True)
    firmware_version = Column(String, nullable=True)
    capabilities = Column(String, nullable=True)  # comma-joined, e.g. "btn_ok,btn_cancel,led_rgb"
    status = Column(String, default="Offline")  # Online | Offline - tracks the parent gateway + last report
    last_seen = Column(DateTime(timezone=True), nullable=True)
    is_simulated = Column(Boolean, default=False)

    gateway = relationship("Gateway", back_populates="zone_modules")
    zone = relationship("Zone", back_populates="zone_module")


class Worker(Base):
    __tablename__ = "workers"

    id = Column(String, primary_key=True, default=_uid)
    name = Column(String, nullable=False)
    color_hex = Column(String, nullable=False, default="#3b82f6")
    active = Column(Boolean, default=True)


class Box(Base):
    """A staged box being tracked through the warehouse."""

    __tablename__ = "boxes"

    id = Column(String, primary_key=True)  # Box ID / barcode value, e.g. "BOX-9928"
    status = Column(String, default="staged")  # staged | picked
    process_stage = Column(String, nullable=True)  # audit/forensic/repair/vendor_return/destroy
    current_zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # True if created by the mock simulator - excluded from Live-mode views
    # so the dashboard/AI reflect only genuine activity once hardware is live.
    is_simulated = Column(Boolean, default=False)


class Job(Base):
    """A queued Store/Pick request working its way through LED-on ->
    (simulated pick/place motion) -> confirm -> LED-off. Persisted so the
    Live Operation Event Stream survives a backend restart and so
    concurrent requests to the same zone are visible in history."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=_uid)
    box_id = Column(String, nullable=False)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    job_type = Column(String, nullable=False)  # STORE | PICK
    status = Column(String, default="QUEUED")  # QUEUED | DONE | FAILED
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    is_simulated = Column(Boolean, default=False)


class Movement(Base):
    """Audit trail: every store/pick event for a box."""

    __tablename__ = "movements"

    id = Column(String, primary_key=True, default=_uid)
    box_id = Column(String, ForeignKey("boxes.id"), nullable=False)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=True)
    event_type = Column(String, nullable=False)  # store | pick | cancel
    method = Column(String, nullable=False, default="qr")  # qr | hardware
    worker_id = Column(String, ForeignKey("workers.id"), nullable=True)
    worker_color = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    is_simulated = Column(Boolean, default=False)


class HeartbeatEvent(Base):
    """Rolling history of gateway heartbeats, used for uptime/health charts."""

    __tablename__ = "heartbeat_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gateway_id = Column(String, ForeignKey("gateways.id"), nullable=False)
    wifi_rssi = Column(Integer, nullable=True)
    uptime_sec = Column(Integer, nullable=True)
    active_nodes_count = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow)


class MqttPayloadLog(Base):
    """
    Rolling log of raw MQTT traffic per gateway, so Settings -> Devices can
    show "what did the hardware actually send/receive" for debugging new
    firmware - pruned to the last N entries per gateway.
    """

    __tablename__ = "mqtt_payload_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gw_id = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)  # "in" (gateway->backend) | "out" (backend->gateway)
    topic = Column(String, nullable=False)
    payload = Column(String, nullable=False)  # raw JSON text
    timestamp = Column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Tiny key/value store for runtime-toggleable settings (e.g. mode)."""

    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
