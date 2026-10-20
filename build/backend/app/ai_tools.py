"""
The set of "tools" (function-calling targets) the AI chatbot is allowed to
use to pull real data out of the dashboard / database.

In Live mode, all of these exclude simulator-generated rows (boxes,
movements, gateways, zone modules) so the assistant only talks about
genuine hardware/API activity once real gear is attached. In Mock mode,
everything is included since that's the point of the demo.
"""
import datetime as dt

from sqlalchemy.orm import Session

from . import models, runtime_state, services


def _live_filtered(query, model):
    """Exclude simulated rows when the app is currently in Live mode."""
    if runtime_state.get_mode() == "live":
        return query.filter(model.is_simulated.is_(False))
    return query


def get_dashboard_stats(db: Session, **_) -> dict:
    staged = _live_filtered(db.query(models.Box).filter(models.Box.status == "staged"), models.Box).count()
    picked_today = _live_filtered(
        db.query(models.Movement)
        .filter(models.Movement.event_type == "pick")
        .filter(models.Movement.timestamp >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)),
        models.Movement,
    ).count()
    online = _live_filtered(db.query(models.Gateway).filter(models.Gateway.status == "Online"), models.Gateway).count()
    offline = _live_filtered(db.query(models.Gateway).filter(models.Gateway.status == "Offline"), models.Gateway).count()
    workers = db.query(models.Worker).filter(models.Worker.active.is_(True)).count()

    return {
        "itemsCurrentlyStaged": staged,
        "itemsPickedLast24h": picked_today,
        "zoneCapacityPct": services.zone_capacity_pct(db),
        "activeWorkers": workers,
        "gatewaysOnline": online,
        "gatewaysOffline": offline,
        "mode": runtime_state.get_mode(),
    }


def locate_box(db: Session, box_id: str = "", **_) -> dict:
    box = services.find_box(db, box_id)
    if not box:
        return {"found": False, "message": f"No box matching '{box_id}' was found."}
    if runtime_state.get_mode() == "live" and box.is_simulated:
        return {"found": False, "message": f"'{box_id}' only exists in simulated data - not visible in Live mode."}

    zone = db.query(models.Zone).filter(models.Zone.id == box.current_zone_id).first() if box.current_zone_id else None
    rack = db.query(models.Rack).filter(models.Rack.id == zone.rack_id).first() if zone else None

    return {
        "found": True,
        "boxId": box.id,
        "status": box.status,
        "zoneId": zone.id if zone else None,
        "zoneName": zone.name if zone else None,
        "rackName": rack.name if rack else None,
        "processStage": box.process_stage,
        "lastUpdated": box.updated_at.isoformat() if box.updated_at else None,
    }


def list_offline_devices(db: Session, **_) -> dict:
    gateways = _live_filtered(db.query(models.Gateway).filter(models.Gateway.status == "Offline"), models.Gateway).all()
    return {
        "count": len(gateways),
        "gateways": [
            {
                "gwId": g.gw_id,
                "rackId": g.rack_id,
                "lastHeartbeat": g.last_heartbeat.isoformat() if g.last_heartbeat else None,
            }
            for g in gateways
        ],
    }


def get_recent_movements(db: Session, limit: int = 5, **_) -> dict:
    limit = max(1, min(int(limit or 5), 25))
    rows = _live_filtered(db.query(models.Movement).order_by(models.Movement.timestamp.desc()), models.Movement).limit(limit).all()
    out = []
    for m in rows:
        zone = db.query(models.Zone).filter(models.Zone.id == m.zone_id).first() if m.zone_id else None
        out.append(
            {
                "boxId": m.box_id,
                "eventType": m.event_type,
                "zoneName": zone.name if zone else None,
                "method": m.method,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            }
        )
    return {"movements": out}


def get_zone_info(db: Session, zone_id: str = "", **_) -> dict:
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        zone = db.query(models.Zone).filter(models.Zone.name.ilike(f"%{zone_id}%")).first()
    if not zone:
        return {"found": False, "message": f"No zone matching '{zone_id}'."}

    rack = db.query(models.Rack).filter(models.Rack.id == zone.rack_id).first()
    boxes = _live_filtered(
        db.query(models.Box).filter(models.Box.current_zone_id == zone.id, models.Box.status == "staged"), models.Box
    ).all()

    return {
        "found": True,
        "zoneId": zone.id,
        "zoneName": zone.name,
        "rackName": rack.name if rack else None,
        "maxBoxes": zone.max_boxes,
        "currentBoxCount": len(boxes),
        "boxIds": [b.id for b in boxes],
        "hasHardware": zone.zone_module is not None,
        "isBarcodeZone": zone.barcode is not None,
    }


def search_boxes(db: Session, query: str = "", **_) -> dict:
    rows = _live_filtered(
        db.query(models.Box).filter(models.Box.id.ilike(f"%{query}%")).order_by(models.Box.updated_at.desc()),
        models.Box,
    ).limit(10).all()
    return {
        "results": [
            {"boxId": b.id, "status": b.status, "zoneId": b.current_zone_id, "processStage": b.process_stage}
            for b in rows
        ]
    }


# ---------------------------------------------------------------- registry

TOOL_IMPLEMENTATIONS = {
    "get_dashboard_stats": get_dashboard_stats,
    "locate_box": locate_box,
    "list_offline_devices": list_offline_devices,
    "get_recent_movements": get_recent_movements,
    "get_zone_info": get_zone_info,
    "search_boxes": search_boxes,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_stats",
            "description": "Get live warehouse KPIs: items currently staged, items picked in the last 24h, zone capacity %, active workers, and gateway online/offline counts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "locate_box",
            "description": "Find the current physical location (rack/zone) and status of a specific box by its Box ID.",
            "parameters": {
                "type": "object",
                "properties": {"box_id": {"type": "string", "description": "The box ID, e.g. BOX-9928"}},
                "required": ["box_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_boxes",
            "description": "Search for boxes whose ID contains a given substring, e.g. to find all boxes when only a partial ID/number is known.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Partial box id or number"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_offline_devices",
            "description": "List all rack Gateways currently offline (missed their heartbeat), useful for maintenance questions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_movements",
            "description": "Get the most recent store/pick events across the whole warehouse.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "How many recent events to return (default 5, max 25)"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_zone_info",
            "description": "Get details about a specific rack zone: capacity, current boxes stored there, and whether it has hardware (RS485 zone module) or is barcode/QR based.",
            "parameters": {
                "type": "object",
                "properties": {"zone_id": {"type": "string", "description": "Zone id or name, e.g. 'Zone 2' or 'A-Mid-2'"}},
                "required": ["zone_id"],
            },
        },
    },
]
