from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..database import get_db
from ..geometry import boxes_overlap, clamp_box_to_bounds
from ..mqtt_client import mqtt_service

router = APIRouter(prefix="/api", tags=["layout"])

FLOORPLAN_COLS = 40
FLOORPLAN_MAX_ROWS = 200


def _zone_to_out(zone: models.Zone) -> schemas.ZoneOut:
    return schemas.ZoneOut(
        id=zone.id,
        rackId=zone.rack_id,
        name=zone.name,
        group=zone.zone_group,
        x=zone.x,
        y=zone.y,
        w=zone.w,
        h=zone.h,
        barcode=zone.barcode,
        defaultLed=zone.default_led,
        maxBoxes=zone.max_boxes,
        nodeUuid=zone.zone_module.node_uuid if zone.zone_module else None,
    )


def _rack_to_out(rack: models.Rack) -> schemas.RackOut:
    return schemas.RackOut(
        id=rack.id, name=rack.name, rows=rack.rows, cols=rack.cols, x=rack.x, y=rack.y, rotation=rack.rotation
    )


def _gateway_to_out(gw: models.Gateway) -> schemas.GatewayOut:
    return schemas.GatewayOut(
        id=gw.id,
        gwId=gw.gw_id,
        rackId=gw.rack_id,
        status=gw.status,
        lastHeartbeat=gw.last_heartbeat,
        wifiRssi=gw.wifi_rssi,
        uptimeSec=gw.uptime_sec,
        activeNodesCount=gw.active_nodes_count,
        isSimulated=gw.is_simulated,
    )


def _module_to_out(m: models.ZoneModule) -> schemas.ZoneModuleOut:
    return schemas.ZoneModuleOut(
        id=m.id,
        nodeUuid=m.node_uuid,
        gatewayId=m.gateway_id,
        gwId=m.gateway.gw_id if m.gateway else None,
        zoneId=m.zone_id,
        daisyChainIndex=m.daisy_chain_index,
        moduleType=m.module_type,
        hardwareRev=m.hardware_rev,
        firmwareVersion=m.firmware_version,
        capabilities=m.capabilities.split(",") if m.capabilities else [],
        status=m.status,
        lastSeen=m.last_seen,
        isSimulated=m.is_simulated,
    )


@router.get("/layout", response_model=schemas.LayoutOut)
def get_layout(db: Session = Depends(get_db)):
    racks = db.query(models.Rack).all()
    zones = db.query(models.Zone).all()
    gateways = db.query(models.Gateway).all()
    modules = db.query(models.ZoneModule).all()
    return schemas.LayoutOut(
        racks=[_rack_to_out(r) for r in racks],
        zones=[_zone_to_out(z) for z in zones],
        gateways=[_gateway_to_out(g) for g in gateways],
        zoneModules=[_module_to_out(m) for m in modules],
    )


@router.post("/layout", response_model=schemas.LayoutOut)
def save_layout(payload: schemas.LayoutIn, db: Session = Depends(get_db)):
    """Full upsert of racks + zones - matches the 'Save Configuration'
    button in the Digital Twin Mapping UI.

    Server-side is the final source of truth for geometry: every zone is
    clamped to fit inside its rack's rows x cols (this is what actually
    fixes "rows says 3 but a 4th row zone got saved" - the frontend also
    constrains interactively, but a client-side glitch can't get past this).
    Rack placements are checked for overlap and nudged to the nearest free
    slot if needed, since racks must never overlap on the floor plan.
    """
    incoming_rack_ids = {r.id for r in payload.racks}
    incoming_zone_ids = {z.id for z in payload.zones}

    for r in db.query(models.Rack).all():
        if r.id not in incoming_rack_ids:
            db.delete(r)
    for z in db.query(models.Zone).all():
        if z.id not in incoming_zone_ids:
            db.delete(z)

    # --- Racks: clamp position, prevent overlap ---
    placed_footprints: list[tuple[int, int, int, int]] = []
    for r_in in payload.racks:
        rack = db.query(models.Rack).filter(models.Rack.id == r_in.id).first()
        if not rack:
            rack = models.Rack(id=r_in.id)
            db.add(rack)
        rack.name = r_in.name
        rack.rows = max(1, r_in.rows)
        rack.cols = max(1, r_in.cols)
        rack.rotation = r_in.rotation or 0

        is_rotated = rack.rotation in (90, 270)
        fw = rack.rows if is_rotated else rack.cols
        fh = rack.cols if is_rotated else rack.rows
        x = max(0, min(FLOORPLAN_COLS - fw, r_in.x or 0))
        y = max(0, r_in.y or 0)

        candidate = (x, y, fw, fh)
        if any(boxes_overlap(candidate, other) for other in placed_footprints):
            x, y = _find_free_floorplan_slot(placed_footprints, fw, fh)
            candidate = (x, y, fw, fh)

        rack.x, rack.y = x, y
        placed_footprints.append(candidate)

    db.flush()

    # --- Zones: clamp to their rack's bounds ---
    racks_by_id = {r.id: r for r in db.query(models.Rack).all()}
    for z_in in payload.zones:
        zone = db.query(models.Zone).filter(models.Zone.id == z_in.id).first()
        if not zone:
            zone = models.Zone(id=z_in.id)
            db.add(zone)

        rack = racks_by_id.get(z_in.rackId)
        x, y, w, h = z_in.x, z_in.y, z_in.w, z_in.h
        if rack:
            x, y, w, h = clamp_box_to_bounds(x, y, w, h, rack.cols, rack.rows)

        zone.rack_id = z_in.rackId
        zone.name = z_in.name
        zone.zone_group = z_in.group
        zone.x, zone.y, zone.w, zone.h = x, y, w, h
        zone.barcode = z_in.barcode
        zone.default_led = z_in.defaultLed or "blue"
        zone.max_boxes = z_in.maxBoxes or 20

    db.commit()
    return get_layout(db)


def _find_free_floorplan_slot(existing: list[tuple[int, int, int, int]], w: int, h: int) -> tuple[int, int]:
    for y in range(0, FLOORPLAN_MAX_ROWS):
        for x in range(0, max(1, FLOORPLAN_COLS - w + 1)):
            candidate = (x, y, w, h)
            if not any(boxes_overlap(candidate, other) for other in existing):
                return x, y
    return 0, 0


@router.post("/zones/{zone_id}/assign", response_model=schemas.ZoneModuleOut)
def assign_zone_module(zone_id: str, payload: schemas.AssignModuleIn, db: Session = Depends(get_db)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(404, f"Zone '{zone_id}' not found")
    module = db.query(models.ZoneModule).filter(models.ZoneModule.id == payload.zoneModuleId).first()
    if not module:
        raise HTTPException(404, f"Zone module '{payload.zoneModuleId}' not found")

    for other in db.query(models.ZoneModule).filter(models.ZoneModule.zone_id == zone_id).all():
        if other.id != module.id:
            other.zone_id = None

    module.zone_id = zone_id
    db.commit()
    db.refresh(module)
    return _module_to_out(module)


@router.post("/zones/{zone_id}/unassign")
def unassign_zone_module(zone_id: str, db: Session = Depends(get_db)):
    modules = db.query(models.ZoneModule).filter(models.ZoneModule.zone_id == zone_id).all()
    for m in modules:
        m.zone_id = None
    db.commit()
    return {"unassigned": len(modules)}


@router.get("/zones/occupancy")
def zones_occupancy(db: Session = Depends(get_db)) -> dict[str, list[schemas.BoxSummary]]:
    occupancy = services.get_zone_occupancy(db)
    return {
        zone_id: [schemas.BoxSummary(boxId=b.id, processStage=b.process_stage, updatedAt=b.updated_at) for b in boxes]
        for zone_id, boxes in occupancy.items()
    }


@router.get("/zones/{zone_id}/boxes", response_model=list[schemas.BoxSummary])
def zone_boxes(zone_id: str, db: Session = Depends(get_db)):
    boxes = services.get_zone_boxes(db, zone_id)
    return [schemas.BoxSummary(boxId=b.id, processStage=b.process_stage, updatedAt=b.updated_at) for b in boxes]
