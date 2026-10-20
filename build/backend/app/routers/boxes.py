from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db
from ..mqtt_client import mqtt_service

router = APIRouter(prefix="/api/boxes", tags=["boxes"])


def _box_location(db: Session, box: models.Box, pending: bool = False) -> schemas.BoxLocationOut:
    zone = db.query(models.Zone).filter(models.Zone.id == box.current_zone_id).first() if box.current_zone_id else None
    rack = db.query(models.Rack).filter(models.Rack.id == zone.rack_id).first() if zone else None
    return schemas.BoxLocationOut(
        boxId=box.id,
        status=box.status,
        zoneId=zone.id if zone else None,
        zoneName=zone.name if zone else None,
        rackId=rack.id if rack else None,
        rackName=rack.name if rack else None,
        processStage=box.process_stage,
        ledColor=zone.default_led if zone else None,
        pendingHardwareConfirm=pending,
    )


@router.get("/", response_model=list[schemas.BoxLocationOut])
def list_staged_boxes(db: Session = Depends(get_db)):
    boxes = db.query(models.Box).filter(models.Box.status == "staged").all()
    return [_box_location(db, b) for b in boxes]


@router.get("/jobs/recent", response_model=list[schemas.JobLogOut])
def recent_jobs(limit: int = 50, db: Session = Depends(get_db)):
    """Recent Store/Pick jobs (queued -> done/failed), newest first - used to
    repopulate the Live Operation Event Stream on page load/refresh."""
    limit = max(1, min(limit, 200))
    jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).limit(limit).all()
    out = []
    for j in jobs:
        zone = db.query(models.Zone).filter(models.Zone.id == j.zone_id).first() if j.zone_id else None
        out.append(
            schemas.JobLogOut(
                id=j.id,
                boxId=j.box_id,
                zoneId=j.zone_id,
                zoneName=zone.name if zone else j.zone_id,
                jobType=j.job_type,
                status=j.status,
                error=j.error,
                createdAt=j.created_at,
                finishedAt=j.finished_at,
            )
        )
    return list(reversed(out))


@router.post("/inbound", response_model=schemas.JobOut)
def inbound(payload: schemas.InboundIn, db: Session = Depends(get_db)):
    """Dashboard's 'Store' button: validates + queues the box, turns the
    zone LED on immediately, and auto-confirms a few seconds later (see
    services.request_store). This is what actually drives the Live
    Operation Event Stream's QUEUED -> PROCESS DONE lines."""
    try:
        services.request_store(db, box_id=payload.boxId, zone_id=payload.zoneId)
    except services.OperationError as exc:
        raise HTTPException(400, str(exc))
    return schemas.JobOut(boxId=payload.boxId, zoneId=payload.zoneId, status="QUEUED")


@router.post("/outbound", response_model=schemas.JobOut)
def outbound(payload: schemas.OutboundIn, db: Session = Depends(get_db)):
    """Dashboard's 'Pickup' button: locates the box, queues the pick, turns
    the zone LED on, and auto-confirms a few seconds later."""
    try:
        box = services.request_pick(db, query=payload.boxId)
    except services.OperationError as exc:
        raise HTTPException(400, str(exc))
    return schemas.JobOut(boxId=box.id, zoneId=box.current_zone_id, status="QUEUED")


@router.post("/store", response_model=schemas.BoxLocationOut)
def store_box(payload: schemas.StoreBoxIn, db: Session = Depends(get_db)):
    """Software-Only (QR) path: worker scans shipping label, then scans the
    shelf's static QR code. This is step 4.1.3 'Green Button (OK)' for the
    QR variant - the React UI POST IS the confirmation (no physical button
    exists on a barcode-only zone)."""
    try:
        box = services.store_box(
            db, box_id=payload.boxId, zone_id=payload.zoneId, method=payload.method, worker_id=payload.workerId
        )
    except services.OperationError as exc:
        raise HTTPException(400, str(exc))
    return _box_location(db, box)


@router.post("/stage", response_model=schemas.BoxLocationOut)
def stage_box(payload: schemas.StageBoxIn, db: Session = Depends(get_db)):
    """Hardware path, step 1 of 2: the Worker Terminal has scanned a box for
    a zone with a real RS485 Zone Module attached. We don't commit yet -
    we register a pending action and wait for the physical Green/Red button
    press to arrive over MQTT (see services.resolve_button_press). Returns
    the box's *prospective* location with pendingHardwareConfirm=true so the
    UI can show "awaiting button press"."""
    zone = db.query(models.Zone).filter(models.Zone.id == payload.zoneId).first()
    if not zone:
        raise HTTPException(404, f"Zone '{payload.zoneId}' not found")

    services.set_pending_action(payload.zoneId, "store", payload.boxId, worker_id=payload.workerId)

    if zone.zone_module and zone.zone_module.gateway:
        mqtt_service.publish_led(
            zone.zone_module.gateway.gw_id, zone.zone_module.node_uuid, zone.default_led or "#3b82f6", "ON"
        )

    box = db.query(models.Box).filter(models.Box.id == payload.boxId).first()
    if box:
        return _box_location(db, box, pending=True)
    return schemas.BoxLocationOut(
        boxId=payload.boxId,
        status="pending",
        zoneId=zone.id,
        zoneName=zone.name,
        rackId=zone.rack_id,
        rackName=None,
        processStage=None,
        ledColor=zone.default_led,
        pendingHardwareConfirm=True,
    )


@router.post("/pick-list", response_model=list[schemas.PickListItemOut])
def pick_list(payload: schemas.PickListIn, db: Session = Depends(get_db)):
    """Proposal 4.2.1: worker/WMS searches an entire truck route at once
    rather than one box at a time. Lights up every matching zone's LED
    immediately and returns a checklist; the UI crosses items off one by
    one via POST /pick/confirm as the worker walks the route."""
    if not payload.boxIds:
        raise HTTPException(400, "At least one box ID is required.")
    return services.build_pick_list(db, payload.boxIds)


@router.post("/search", response_model=schemas.BoxLocationOut)
def search_box(payload: schemas.SearchBoxIn, db: Session = Depends(get_db)):
    """Pick path step 1: worker or WMS searches for a box; the response
    tells the frontend which rack/zone to highlight. For hardware zones,
    this also arms a pending 'pick' action (see stage_box docstring) and
    turns the LED on, so the next Green button press at that zone confirms
    the pick without needing another API round-trip."""
    box = services.find_box(db, payload.query)
    if not box or box.status != "staged":
        raise HTTPException(404, f"No staged box matching '{payload.query}' was found.")

    zone = db.query(models.Zone).filter(models.Zone.id == box.current_zone_id).first() if box.current_zone_id else None
    if zone and zone.zone_module and zone.zone_module.gateway:
        services.set_pending_action(zone.id, "pick", box.id)
        mqtt_service.publish_led(zone.zone_module.gateway.gw_id, zone.zone_module.node_uuid, zone.default_led or "#3b82f6", "ON")

    return _box_location(db, box, pending=bool(zone and zone.zone_module))


@router.post("/pick/confirm", response_model=schemas.BoxLocationOut)
def confirm_pick(payload: schemas.PickConfirmIn, db: Session = Depends(get_db)):
    """Direct confirmation from the UI (used by Live Ops' 'Confirm Pickup'
    button, and by the mock simulator). This is an explicit override that
    doesn't require a physical button - handy for testing without hardware
    attached, or for barcode-only zones which have no button at all."""
    box = db.query(models.Box).filter(models.Box.id == payload.boxId).first()
    zone_id = box.current_zone_id if box else None

    try:
        box = services.confirm_pick(db, box_id=payload.boxId, worker_id=payload.workerId)
    except services.OperationError as exc:
        raise HTTPException(400, str(exc))

    if zone_id:
        services.clear_pending_action(zone_id)
        zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
        if zone and zone.zone_module and zone.zone_module.gateway:
            mqtt_service.publish_led(zone.zone_module.gateway.gw_id, zone.zone_module.node_uuid, "#000000", "OFF")

    return _box_location(db, box)


@router.get("/{box_id}/history", response_model=list[schemas.MovementOut])
def box_history(box_id: str, db: Session = Depends(get_db)):
    """Proposal 4.1.4 'full traceability': every store/pick/cancel event
    ever recorded for this specific box, newest first."""
    box = db.query(models.Box).filter(models.Box.id == box_id).first()
    if not box:
        raise HTTPException(404, f"Box '{box_id}' not found")

    rows = (
        db.query(models.Movement)
        .filter(models.Movement.box_id == box_id)
        .order_by(models.Movement.timestamp.desc())
        .all()
    )

    out = []
    for m in rows:
        zone = db.query(models.Zone).filter(models.Zone.id == m.zone_id).first() if m.zone_id else None
        rack = db.query(models.Rack).filter(models.Rack.id == zone.rack_id).first() if zone else None
        worker = db.query(models.Worker).filter(models.Worker.id == m.worker_id).first() if m.worker_id else None

        verb = {"store": "stored at", "pick": "picked and removed from"}.get(m.event_type, "cancelled at")
        location = f"{rack.name}, {zone.name}" if rack and zone else (zone.name if zone else "an unknown location")

        out.append(
            schemas.MovementOut(
                id=m.id,
                boxId=m.box_id,
                eventType=m.event_type,
                method=m.method,
                zoneId=zone.id if zone else None,
                zoneName=zone.name if zone else None,
                rackId=rack.id if rack else None,
                rackName=rack.name if rack else None,
                workerId=worker.id if worker else None,
                workerName=worker.name if worker else None,
                timestamp=m.timestamp,
                summary=f"Box {m.box_id} {verb} {location}.",
            )
        )
    return out


@router.get("/{box_id}", response_model=schemas.BoxLocationOut)
def get_box(box_id: str, db: Session = Depends(get_db)):
    box = db.query(models.Box).filter(models.Box.id == box_id).first()
    if not box:
        raise HTTPException(404, f"Box '{box_id}' not found")
    return _box_location(db, box)
