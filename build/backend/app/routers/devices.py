from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..mqtt_client import mqtt_service
from .layout import _gateway_to_out, _module_to_out

router = APIRouter(prefix="/api", tags=["devices"])


# ---------------------------------------------------------------- gateways

@router.get("/gateways", response_model=list[schemas.GatewayOut])
def list_gateways(db: Session = Depends(get_db)):
    return [_gateway_to_out(g) for g in db.query(models.Gateway).all()]


@router.post("/gateways", response_model=schemas.GatewayOut)
def add_gateway(payload: schemas.AddGatewayIn, db: Session = Depends(get_db)):
    existing = db.query(models.Gateway).filter(models.Gateway.gw_id == payload.gwId).first()
    if existing:
        raise HTTPException(409, f"Gateway '{payload.gwId}' already exists.")
    gw = models.Gateway(gw_id=payload.gwId, rack_id=payload.rackId, status="Offline")
    db.add(gw)
    db.commit()
    db.refresh(gw)
    return _gateway_to_out(gw)


@router.delete("/gateways/{gateway_id}")
def remove_gateway(gateway_id: str, db: Session = Depends(get_db)):
    gw = db.query(models.Gateway).filter(models.Gateway.id == gateway_id).first()
    if not gw:
        raise HTTPException(404, f"Gateway '{gateway_id}' not found")
    db.delete(gw)
    db.commit()
    return {"deleted": True}


@router.post("/gateways/{gw_id}/ping", response_model=schemas.PingGatewayOut)
def ping_gateway(gw_id: str, db: Session = Depends(get_db)):
    """Publishes an optional rx/ping convenience command (not in the base
    hardware spec - real firmware that doesn't implement it will simply
    ignore it, and the UI falls back to waiting for the next heartbeat)."""
    gw = db.query(models.Gateway).filter(models.Gateway.gw_id == gw_id).first()
    if not gw:
        raise HTTPException(404, f"Gateway '{gw_id}' not found")
    mqtt_service.publish_ping(gw_id)
    return schemas.PingGatewayOut(published=True, mqttConnected=mqtt_service.connected)


@router.get("/gateways/{gw_id}/payload-log", response_model=list[schemas.PayloadLogEntry])
def gateway_payload_log(gw_id: str, limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    rows = (
        db.query(models.MqttPayloadLog)
        .filter(models.MqttPayloadLog.gw_id == gw_id)
        .order_by(models.MqttPayloadLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        schemas.PayloadLogEntry(direction=r.direction, topic=r.topic, payload=r.payload, timestamp=r.timestamp)
        for r in rows
    ]


# ------------------------------------------------------------- zone modules

@router.get("/zone-modules", response_model=list[schemas.ZoneModuleOut])
def list_zone_modules(db: Session = Depends(get_db)):
    return [_module_to_out(m) for m in db.query(models.ZoneModule).all()]


@router.post("/zone-modules", response_model=schemas.ZoneModuleOut)
def add_zone_module(payload: schemas.AddZoneModuleIn, db: Session = Depends(get_db)):
    existing = db.query(models.ZoneModule).filter(models.ZoneModule.node_uuid == payload.nodeUuid).first()
    if existing:
        raise HTTPException(409, f"Zone module '{payload.nodeUuid}' already exists.")
    gateway = db.query(models.Gateway).filter(models.Gateway.id == payload.gatewayId).first()
    if not gateway:
        raise HTTPException(404, f"Gateway '{payload.gatewayId}' not found")

    module = models.ZoneModule(
        node_uuid=payload.nodeUuid,
        gateway_id=payload.gatewayId,
        module_type=payload.moduleType or "Medium Module",
        hardware_rev=payload.hardwareRev,
        capabilities=",".join(payload.capabilities) if payload.capabilities else None,
        status="Online",
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return _module_to_out(module)


@router.patch("/zone-modules/{module_id}", response_model=schemas.ZoneModuleOut)
def update_zone_module(module_id: str, payload: schemas.UpdateZoneModuleIn, db: Session = Depends(get_db)):
    module = db.query(models.ZoneModule).filter(models.ZoneModule.id == module_id).first()
    if not module:
        raise HTTPException(404, f"Zone module '{module_id}' not found")
    if payload.moduleType is not None:
        module.module_type = payload.moduleType
    if payload.hardwareRev is not None:
        module.hardware_rev = payload.hardwareRev
    db.commit()
    db.refresh(module)
    return _module_to_out(module)


@router.delete("/zone-modules/{module_id}")
def remove_zone_module(module_id: str, db: Session = Depends(get_db)):
    module = db.query(models.ZoneModule).filter(models.ZoneModule.id == module_id).first()
    if not module:
        raise HTTPException(404, f"Zone module '{module_id}' not found")
    db.delete(module)
    db.commit()
    return {"deleted": True}


@router.post("/zone-modules/{module_id}/identify")
def identify_zone_module(module_id: str, db: Session = Depends(get_db)):
    module = db.query(models.ZoneModule).filter(models.ZoneModule.id == module_id).first()
    if not module:
        raise HTTPException(404, f"Zone module '{module_id}' not found")
    gateway = db.query(models.Gateway).filter(models.Gateway.id == module.gateway_id).first()
    if gateway:
        mqtt_service.publish_identify(gateway.gw_id, module.node_uuid)
    return {"ok": True, "mqttConnected": mqtt_service.connected}
