"""
Core Store / Pick workflow logic (see proposal section 4 / template section 7:
"System Data Flow"). Shared by:
  - REST endpoints (Software-Only / QR path: React UI calls these directly)
  - The MQTT button handler (Smart PTL path)

Keeping one code path for both means Package A (QR only) and Package B/C
(hardware buttons) produce identical, consistent data in the database.

--- Why a "pending action" registry exists ---
Per the real hardware protocol, a physical button press payload only tells
us *which button* was pressed on *which node* - it carries no box_id:

    {"event": "button_press", "node_uuid": "ZMOD-4491-B7", "button": "OK_GREEN", ...}

The box_id only ever comes from the Worker Terminal's barcode scan (Store
flow) or from a warehouse search (Pick flow). So the backend has to
remember "this zone is expecting a button press for box X" between that
scan/search and the physical press - that's what PendingAction is for. It's
short-lived and in-memory (a single backend process), mirroring the
Gateway's own LED `timeout_ms` fail-safe.
"""
import datetime as dt
import logging
import threading
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from . import models
from .events import broadcast_threadsafe

logger = logging.getLogger("smart_warehouse.services")


class OperationError(Exception):
    pass


def _zone_with_rack(db: Session, zone_id: str) -> tuple[models.Zone | None, models.Rack | None]:
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        return None, None
    rack = db.query(models.Rack).filter(models.Rack.id == zone.rack_id).first()
    return zone, rack


def store_box(
    db: Session,
    box_id: str,
    zone_id: str,
    method: str = "qr",
    worker_id: str | None = None,
    is_simulated: bool = False,
) -> models.Box:
    zone, _ = _zone_with_rack(db, zone_id)
    if not zone:
        raise OperationError(f"Zone '{zone_id}' does not exist.")

    box = db.query(models.Box).filter(models.Box.id == box_id).first()
    if not box:
        box = models.Box(id=box_id, status="staged", current_zone_id=zone_id, is_simulated=is_simulated)
        db.add(box)
    else:
        box.status = "staged"
        box.current_zone_id = zone_id
        box.is_simulated = is_simulated
        box.updated_at = dt.datetime.now(dt.timezone.utc)

    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first() if worker_id else None

    movement = models.Movement(
        box_id=box_id,
        zone_id=zone_id,
        event_type="store",
        method=method,
        worker_id=worker.id if worker else None,
        worker_color=worker.color_hex if worker else None,
        is_simulated=is_simulated,
    )
    db.add(movement)
    db.commit()
    db.refresh(box)

    broadcast_threadsafe({"type": "box_stored", "boxId": box_id, "zoneId": zone_id, "method": method})
    return box


def find_box(db: Session, query: str) -> models.Box | None:
    query = query.strip()
    if not query:
        return None
    box = db.query(models.Box).filter(models.Box.id == query).first()
    if box:
        return box
    return (
        db.query(models.Box)
        .filter(models.Box.id.ilike(f"%{query}%"))
        .order_by(models.Box.updated_at.desc())
        .first()
    )


def build_pick_list(db: Session, queries: list[str]) -> list[dict]:
    """Resolve a whole truck route's worth of box IDs at once (proposal
    4.2.1): locates each box, turns on the LED for every matching zone
    immediately (so the whole route lights up at once, not one at a time),
    and arms a pending hardware-button confirm for zones that have one.
    Returns a checklist the Worker Terminal UI can render and cross off
    item-by-item via confirm_pick."""
    from .mqtt_client import mqtt_service

    results: list[dict] = []
    lit_zone_ids: set[str] = set()

    for query in queries:
        query = (query or "").strip()
        if not query:
            continue

        box = find_box(db, query)
        if not box or box.status != "staged":
            results.append({"query": query, "found": False, "message": f"No staged box matching '{query}'."})
            continue

        zone, rack = _zone_with_rack(db, box.current_zone_id) if box.current_zone_id else (None, None)
        if zone and zone.id not in lit_zone_ids:
            mqtt_service.publish_led_for_zone(db, zone.id, zone.default_led or "#3b82f6", "ON")
            lit_zone_ids.add(zone.id)
        if zone and zone.zone_module and zone.zone_module.gateway:
            set_pending_action(zone.id, "pick", box.id)

        results.append(
            {
                "query": query,
                "found": True,
                "boxId": box.id,
                "status": box.status,
                "zoneId": zone.id if zone else None,
                "zoneName": zone.name if zone else None,
                "rackId": rack.id if rack else None,
                "rackName": rack.name if rack else None,
                "ledColor": zone.default_led if zone else None,
            }
        )

    return results


def confirm_pick(
    db: Session,
    box_id: str,
    worker_id: str | None = None,
    is_simulated: bool = False,
) -> models.Box:
    box = db.query(models.Box).filter(models.Box.id == box_id).first()
    if not box:
        raise OperationError(f"Box '{box_id}' not found.")

    zone_id = box.current_zone_id
    box.status = "picked"
    box.current_zone_id = None
    box.updated_at = dt.datetime.now(dt.timezone.utc)

    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first() if worker_id else None

    movement = models.Movement(
        box_id=box_id,
        zone_id=zone_id,
        event_type="pick",
        method="hardware" if worker_id else "qr",
        worker_id=worker.id if worker else None,
        worker_color=worker.color_hex if worker else None,
        is_simulated=is_simulated,
    )
    db.add(movement)
    db.commit()
    db.refresh(box)

    broadcast_threadsafe({"type": "box_picked", "boxId": box_id, "zoneId": zone_id})
    return box


# ---------------------------------------------------------------------------
# Queue + auto-confirm flow: this deployment's zone modules are simple
# MQTT-controlled LED cubbies with no physical confirm button wired back to
# the backend (unlike the RS485/Gateway hardware the pending-action system
# above supports). So a Store/Pick request is handled as:
#   1. immediately validate + turn the zone's LED on + log "QUEUED"
#   2. after CONFIRM_DELAY_SEC (simulating the pick/place motion), commit the
#      DB write, turn the LED off, and log "PROCESS DONE"
# This mirrors the original worker.js's SIMULATED_DELAY_MS behaviour, but is
# now driven by real persisted Jobs instead of an in-memory Redis queue.
# ---------------------------------------------------------------------------

CONFIRM_DELAY_SEC = 5.0


def request_store(db: Session, box_id: str, zone_id: str, is_simulated: bool = False) -> models.Zone:
    from .mqtt_client import mqtt_service

    zone, rack = _zone_with_rack(db, zone_id)
    if not zone:
        raise OperationError(f"Zone '{zone_id}' does not exist.")

    existing = db.query(models.Box).filter(models.Box.id == box_id).first()
    if existing and existing.status == "staged":
        raise OperationError(f"Box '{box_id}' already exists in the warehouse.")

    staged_count = (
        db.query(models.Box).filter(models.Box.current_zone_id == zone_id, models.Box.status == "staged").count()
    )
    if staged_count >= (zone.max_boxes or 20):
        raise OperationError(f"Zone '{zone_id}' has reached full capacity ({staged_count}/{zone.max_boxes}).")

    job = models.Job(box_id=box_id, zone_id=zone_id, job_type="STORE", status="QUEUED", is_simulated=is_simulated)
    db.add(job)
    db.commit()
    db.refresh(job)

    mqtt_service.publish_led_for_zone(db, zone_id, zone.default_led or "#3b82f6", "ON")
    broadcast_threadsafe(
        {
            "type": "job_queued",
            "jobType": "STORE",
            "boxId": box_id,
            "zoneId": zone_id,
            "zoneName": zone.name,
            "capacity": f"{staged_count + 1}/{zone.max_boxes or 20}",
        }
    )

    timer = threading.Timer(CONFIRM_DELAY_SEC, _finish_store, args=(job.id,))
    timer.daemon = True
    timer.start()
    return zone


def _finish_store(job_id: str) -> None:
    from .database import session_scope
    from .mqtt_client import mqtt_service

    with session_scope() as db:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job or job.status != "QUEUED":
            return
        try:
            store_box(db, job.box_id, job.zone_id, method="hardware", is_simulated=job.is_simulated)
        except OperationError as exc:
            job.status = "FAILED"
            job.error = str(exc)
            db.commit()
            broadcast_threadsafe({"type": "job_failed", "jobType": "STORE", "boxId": job.box_id, "reason": str(exc)})
            return
        job.status = "DONE"
        job.finished_at = utcnow()
        db.commit()
        mqtt_service.publish_led_for_zone(db, job.zone_id, "#000000", "OFF")
        remaining = (
            db.query(models.Box).filter(models.Box.current_zone_id == job.zone_id, models.Box.status == "staged").count()
        )
        zone = db.query(models.Zone).filter(models.Zone.id == job.zone_id).first()
        broadcast_threadsafe(
            {
                "type": "job_done",
                "jobType": "STORE",
                "boxId": job.box_id,
                "zoneId": job.zone_id,
                "zoneName": zone.name if zone else job.zone_id,
                "capacity": f"{remaining}/{zone.max_boxes if zone else 20}",
            }
        )


def request_pick(db: Session, query: str, is_simulated: bool = False) -> models.Box:
    from .mqtt_client import mqtt_service

    box = find_box(db, query)
    if not box or box.status != "staged":
        raise OperationError(f"No staged box matching '{query}' was found.")

    zone = db.query(models.Zone).filter(models.Zone.id == box.current_zone_id).first() if box.current_zone_id else None

    job = models.Job(box_id=box.id, zone_id=box.current_zone_id, job_type="PICK", status="QUEUED", is_simulated=is_simulated)
    db.add(job)
    db.commit()
    db.refresh(job)

    if zone:
        mqtt_service.publish_led_for_zone(db, zone.id, zone.default_led or "#3b82f6", "ON")
    broadcast_threadsafe(
        {"type": "job_queued", "jobType": "PICK", "boxId": box.id, "zoneId": box.current_zone_id, "zoneName": zone.name if zone else "-"}
    )

    timer = threading.Timer(CONFIRM_DELAY_SEC, _finish_pick, args=(job.id,))
    timer.daemon = True
    timer.start()
    return box


def _finish_pick(job_id: str) -> None:
    from .database import session_scope
    from .mqtt_client import mqtt_service

    with session_scope() as db:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job or job.status != "QUEUED":
            return
        zone_id = job.zone_id
        try:
            confirm_pick(db, job.box_id, is_simulated=job.is_simulated)
        except OperationError as exc:
            job.status = "FAILED"
            job.error = str(exc)
            db.commit()
            broadcast_threadsafe({"type": "job_failed", "jobType": "PICK", "boxId": job.box_id, "reason": str(exc)})
            return
        job.status = "DONE"
        job.finished_at = utcnow()
        db.commit()
        if zone_id:
            mqtt_service.publish_led_for_zone(db, zone_id, "#000000", "OFF")
        remaining = (
            db.query(models.Box).filter(models.Box.current_zone_id == zone_id, models.Box.status == "staged").count()
            if zone_id
            else 0
        )
        zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first() if zone_id else None
        broadcast_threadsafe(
            {
                "type": "job_done",
                "jobType": "PICK",
                "boxId": job.box_id,
                "zoneId": zone_id,
                "zoneName": zone.name if zone else "-",
                "capacity": f"{remaining}/{zone.max_boxes if zone else 20}" if zone else None,
            }
        )


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def zone_capacity_pct(db: Session) -> int:
    from . import runtime_state  # local import to avoid a circular import at module load time

    total_capacity = sum(z.max_boxes or 1 for z in db.query(models.Zone).all())
    if total_capacity == 0:
        return 0
    staged_query = db.query(models.Box).filter(models.Box.status == "staged")
    if runtime_state.get_mode() == "live":
        staged_query = staged_query.filter(models.Box.is_simulated.is_(False))
    staged = staged_query.count()
    return int(min(100, round(100 * staged / total_capacity)))


def get_zone_boxes(db: Session, zone_id: str) -> list[models.Box]:
    from . import runtime_state

    query = db.query(models.Box).filter(models.Box.current_zone_id == zone_id, models.Box.status == "staged")
    if runtime_state.get_mode() == "live":
        query = query.filter(models.Box.is_simulated.is_(False))
    return query.order_by(models.Box.updated_at.desc()).all()


def get_zone_occupancy(db: Session) -> dict[str, list[models.Box]]:
    from . import runtime_state

    query = db.query(models.Box).filter(models.Box.status == "staged")
    if runtime_state.get_mode() == "live":
        query = query.filter(models.Box.is_simulated.is_(False))
    boxes = query.all()
    out: dict[str, list[models.Box]] = {}
    for b in boxes:
        if not b.current_zone_id:
            continue
        out.setdefault(b.current_zone_id, []).append(b)
    return out


# ---------------------------------------------------------------------------
# Pending action registry - bridges "scan/search" (which knows the box_id)
# and "physical button press" (which doesn't).
# ---------------------------------------------------------------------------

PendingType = Literal["store", "pick"]


@dataclass
class PendingAction:
    zone_id: str
    action_type: PendingType
    box_id: str
    worker_id: str | None
    expires_at: dt.datetime


_pending_lock = threading.Lock()
_pending: dict[str, PendingAction] = {}  # zone_id -> PendingAction

DEFAULT_PENDING_TTL_SEC = 30


def set_pending_action(
    zone_id: str, action_type: PendingType, box_id: str, worker_id: str | None = None, ttl_sec: int = DEFAULT_PENDING_TTL_SEC
) -> None:
    with _pending_lock:
        _pending[zone_id] = PendingAction(
            zone_id=zone_id,
            action_type=action_type,
            box_id=box_id,
            worker_id=worker_id,
            expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ttl_sec),
        )
    broadcast_threadsafe({"type": "pending_action", "zoneId": zone_id, "actionType": action_type, "boxId": box_id})


def get_pending_action(zone_id: str) -> PendingAction | None:
    with _pending_lock:
        action = _pending.get(zone_id)
        if action and action.expires_at < dt.datetime.now(dt.timezone.utc):
            del _pending[zone_id]
            return None
        return action


def clear_pending_action(zone_id: str) -> None:
    with _pending_lock:
        _pending.pop(zone_id, None)
    broadcast_threadsafe({"type": "pending_action_cleared", "zoneId": zone_id})


def resolve_button_press(
    db: Session, zone_id: str, button: str, is_simulated: bool = False
) -> dict:
    """
    Resolve a physical OK_GREEN / CANCEL_RED press at a zone against
    whatever is pending there. Returns a small result dict for logging;
    never raises for "nothing pending" - that's a normal/expected case
    (e.g. a stray button press).
    """
    button = (button or "").upper()
    pending = get_pending_action(zone_id)

    if button == "CANCEL_RED":
        if pending:
            clear_pending_action(zone_id)
            return {"resolved": True, "action": "cancel", "boxId": pending.box_id}
        return {"resolved": False, "reason": "no_pending_action"}

    if button != "OK_GREEN":
        return {"resolved": False, "reason": f"unknown_button:{button}"}

    if not pending:
        return {"resolved": False, "reason": "no_pending_action"}

    clear_pending_action(zone_id)
    try:
        if pending.action_type == "store":
            store_box(db, pending.box_id, zone_id, method="hardware", worker_id=pending.worker_id, is_simulated=is_simulated)
            return {"resolved": True, "action": "store", "boxId": pending.box_id}
        else:
            confirm_pick(db, pending.box_id, worker_id=pending.worker_id, is_simulated=is_simulated)
            return {"resolved": True, "action": "pick", "boxId": pending.box_id}
    except OperationError as exc:
        return {"resolved": False, "reason": str(exc)}
