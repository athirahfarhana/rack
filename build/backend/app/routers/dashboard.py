import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, runtime_state, schemas, services
from ..database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _live_filtered(query, model):
    """Exclude simulator-generated rows when currently in Live mode, so the
    dashboard reflects only genuine hardware/API activity."""
    if runtime_state.get_mode() == "live":
        return query.filter(model.is_simulated.is_(False))
    return query


@router.get("/stats", response_model=schemas.DashboardStatsOut)
def get_stats(db: Session = Depends(get_db)):
    staged = _live_filtered(db.query(models.Box).filter(models.Box.status == "staged"), models.Box).count()

    pending_jobs = _live_filtered(db.query(models.Job).filter(models.Job.status == "QUEUED"), models.Job).count()

    processing_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=15)
    items_processing = _live_filtered(
        db.query(models.Movement)
        .filter(models.Movement.event_type == "pick")
        .filter(models.Movement.timestamp >= processing_cutoff),
        models.Movement,
    ).count()

    online = _live_filtered(db.query(models.Gateway).filter(models.Gateway.status == "Online"), models.Gateway).count()
    offline = _live_filtered(db.query(models.Gateway).filter(models.Gateway.status == "Offline"), models.Gateway).count()
    active_workers = db.query(models.Worker).filter(models.Worker.active.is_(True)).count()

    recent = _live_filtered(db.query(models.Movement).order_by(models.Movement.timestamp.desc()), models.Movement).limit(8).all()
    recent_out = []
    for m in recent:
        zone = db.query(models.Zone).filter(models.Zone.id == m.zone_id).first() if m.zone_id else None
        worker = db.query(models.Worker).filter(models.Worker.id == m.worker_id).first() if m.worker_id else None
        recent_out.append(
            schemas.RecentPickOut(
                boxId=m.box_id,
                time=m.timestamp.strftime("%H:%M:%S") if m.timestamp else "",
                zone=zone.name if zone else "-",
                worker=worker.name if worker else "System",
                eventType=m.event_type,
            )
        )

    alerts: list[schemas.AlertOut] = []
    offline_gateways = _live_filtered(
        db.query(models.Gateway).filter(models.Gateway.status == "Offline"), models.Gateway
    ).all()
    for g in offline_gateways[:5]:
        alerts.append(
            schemas.AlertOut(
                level="critical",
                title="Gateway Offline",
                message=f"Gateway {g.gw_id} is offline. Heartbeat timeout - check WiFi/power at the rack.",
                time=g.last_heartbeat.strftime("%H:%M:%S") if g.last_heartbeat else "unknown",
            )
        )
    capacity_pct = services.zone_capacity_pct(db)
    if capacity_pct >= 90:
        alerts.append(
            schemas.AlertOut(
                level="warning",
                title="Zone Capacity High",
                message=f"Staging zones are at {capacity_pct}% capacity. Consider adding racks or clearing staged boxes.",
                time=dt.datetime.now().strftime("%H:%M:%S"),
            )
        )

    return schemas.DashboardStatsOut(
        itemsStored=staged,
        itemsProcessing=items_processing,
        pendingJobs=pending_jobs,
        capacityPct=capacity_pct,
        activeWorkers=active_workers,
        devicesOnline=online,
        devicesOffline=offline,
        recentPicks=recent_out,
        alerts=alerts,
        mode=runtime_state.get_mode(),
    )
