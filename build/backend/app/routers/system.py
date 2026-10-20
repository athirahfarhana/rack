from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, ollama_client, runtime_state, schemas
from ..config import settings
from ..database import get_db
from ..mqtt_client import mqtt_service

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/mode", response_model=schemas.ModeOut)
async def get_mode():
    return schemas.ModeOut(
        mode=runtime_state.get_mode(),
        mqttConnected=mqtt_service.connected,
        ollamaReachable=await ollama_client.is_reachable(),
    )


@router.post("/mode", response_model=schemas.ModeOut)
async def set_mode(payload: schemas.ModeIn):
    try:
        runtime_state.set_mode(payload.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return await get_mode()


@router.get("/events/recent")
def recent_events(limit: int = 40, db: Session = Depends(get_db)):
    """Replays the most recent Jobs (queued/done/failed) as event-stream
    lines, so the Live Operation panel isn't empty on first page load -
    everything after that arrives live over /ws/events."""
    limit = max(1, min(limit, 200))
    jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).limit(limit).all()
    out = []
    for job in reversed(jobs):
        zone = db.query(models.Zone).filter(models.Zone.id == job.zone_id).first() if job.zone_id else None
        out.append(
            {
                "type": "job_queued",
                "jobType": job.job_type,
                "boxId": job.box_id,
                "zoneId": job.zone_id,
                "zoneName": zone.name if zone else job.zone_id,
                "timestamp": job.created_at.isoformat() if job.created_at else None,
            }
        )
        if job.status == "DONE":
            out.append(
                {
                    "type": "job_done",
                    "jobType": job.job_type,
                    "boxId": job.box_id,
                    "zoneId": job.zone_id,
                    "zoneName": zone.name if zone else job.zone_id,
                    "timestamp": job.finished_at.isoformat() if job.finished_at else None,
                }
            )
        elif job.status == "FAILED":
            out.append(
                {
                    "type": "job_failed",
                    "jobType": job.job_type,
                    "boxId": job.box_id,
                    "reason": job.error,
                    "timestamp": job.finished_at.isoformat() if job.finished_at else None,
                }
            )
    return out


@router.get("/workers", response_model=list[schemas.WorkerOut])
def list_workers(db: Session = Depends(get_db)):
    workers = db.query(models.Worker).all()
    return [
        schemas.WorkerOut(id=w.id, name=w.name, colorHex=w.color_hex, active=w.active)
        for w in workers
    ]


@router.get("/system/config", response_model=schemas.SystemConfigOut)
def system_config():
    """Non-secret config surfaced read-only in the Settings tab, so it's
    obvious *where* to change it (backend/.env) without exposing anything
    sensitive over the API."""
    return schemas.SystemConfigOut(
        mqttHost=settings.MQTT_HOST,
        mqttPort=settings.MQTT_PORT,
        mqttTopicPrefix=settings.MQTT_TOPIC_PREFIX,
        mqttEnabled=settings.MQTT_ENABLED,
        heartbeatTimeoutSec=settings.HEARTBEAT_OFFLINE_TIMEOUT_SEC,
        ollamaHost=settings.OLLAMA_HOST,
        ollamaModel=settings.OLLAMA_MODEL,
    )


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "mode": runtime_state.get_mode(),
        "mqttConnected": mqtt_service.connected,
        "ollamaReachable": await ollama_client.is_reachable(),
        "ollamaModel": settings.OLLAMA_MODEL,
    }
