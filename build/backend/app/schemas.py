import datetime as dt

from pydantic import BaseModel, Field


# ---------- Gateways / Zone Modules ----------

class GatewayOut(BaseModel):
    id: str
    gwId: str
    rackId: str | None = None
    status: str
    lastHeartbeat: dt.datetime | None = None
    wifiRssi: int | None = None
    uptimeSec: int | None = None
    activeNodesCount: int | None = None
    isSimulated: bool = False

    class Config:
        from_attributes = True


class ZoneModuleOut(BaseModel):
    id: str
    nodeUuid: str
    gatewayId: str
    gwId: str | None = None
    zoneId: str | None = None
    daisyChainIndex: int | None = None
    moduleType: str | None = "Medium Module"
    hardwareRev: str | None = None
    firmwareVersion: str | None = None
    capabilities: list[str] = []
    status: str
    lastSeen: dt.datetime | None = None
    isSimulated: bool = False


class AddGatewayIn(BaseModel):
    gwId: str
    rackId: str | None = None


class AddZoneModuleIn(BaseModel):
    nodeUuid: str
    gatewayId: str
    moduleType: str | None = "Medium Module"
    hardwareRev: str | None = None
    capabilities: list[str] = []


class UpdateZoneModuleIn(BaseModel):
    moduleType: str | None = None
    hardwareRev: str | None = None


class PingGatewayOut(BaseModel):
    published: bool
    mqttConnected: bool


class PayloadLogEntry(BaseModel):
    direction: str
    topic: str
    payload: str
    timestamp: dt.datetime


# ---------- Layout: Racks / Zones ----------

class ZoneIn(BaseModel):
    id: str
    rackId: str
    name: str
    group: str | None = None  # maps to Zone.zone_group
    x: int
    y: int
    w: int
    h: int
    barcode: str | None = None
    defaultLed: str | None = "blue"
    maxBoxes: int | None = 20


class ZoneOut(ZoneIn):
    nodeUuid: str | None = None


class RackIn(BaseModel):
    id: str
    name: str
    rows: int
    cols: int
    x: int | None = 0
    y: int | None = 0
    rotation: int | None = 0


class RackOut(RackIn):
    pass


class LayoutIn(BaseModel):
    racks: list[RackIn]
    zones: list[ZoneIn]


class LayoutOut(BaseModel):
    racks: list[RackOut]
    zones: list[ZoneOut]
    gateways: list[GatewayOut]
    zoneModules: list[ZoneModuleOut]


class AssignModuleIn(BaseModel):
    zoneModuleId: str


# ---------- Boxes / Store & Pick workflow ----------

class InboundIn(BaseModel):
    boxId: str = Field(..., description="Box ID typed/scanned into the Inbound panel")
    zoneId: str = Field(..., description="Target zone selected in the dropdown")


class OutboundIn(BaseModel):
    boxId: str = Field(..., description="Box ID typed/scanned into the Outbound panel")


class JobOut(BaseModel):
    boxId: str
    zoneId: str | None = None
    status: str


class JobLogOut(BaseModel):
    id: str
    boxId: str
    zoneId: str | None = None
    zoneName: str | None = None
    jobType: str
    status: str
    error: str | None = None
    createdAt: dt.datetime
    finishedAt: dt.datetime | None = None


class StoreBoxIn(BaseModel):
    boxId: str = Field(..., description="Scanned Box ID / barcode")
    zoneId: str
    workerId: str | None = None
    method: str = "qr"  # qr | hardware


class StageBoxIn(BaseModel):
    """Software has scanned a box for a hardware zone but is waiting on the
    physical Green button press to confirm - see services.PendingAction."""

    boxId: str
    zoneId: str
    workerId: str | None = None


class SearchBoxIn(BaseModel):
    query: str


class PickConfirmIn(BaseModel):
    boxId: str
    workerId: str | None = None


class PickListIn(BaseModel):
    """A whole truck route's worth of box IDs searched at once - proposal
    4.2.1 ('load a specific item or an entire truck route')."""

    boxIds: list[str] = Field(..., description="Box IDs (or partial matches) making up this pick route")


class PickListItemOut(BaseModel):
    query: str
    found: bool
    boxId: str | None = None
    status: str | None = None
    zoneId: str | None = None
    zoneName: str | None = None
    rackId: str | None = None
    rackName: str | None = None
    ledColor: str | None = None
    message: str | None = None


class BoxLocationOut(BaseModel):
    boxId: str
    status: str
    zoneId: str | None
    zoneName: str | None
    rackId: str | None
    rackName: str | None
    processStage: str | None
    ledColor: str | None = None
    pendingHardwareConfirm: bool = False


class MovementOut(BaseModel):
    """One entry in a box's full audit trail (proposal 4.1.4 'full
    traceability'). `summary` mirrors the proposal's own example record
    format, e.g. "Box X stored at Rack A, Middle Shelf, Zone 2."."""

    id: str
    boxId: str
    eventType: str  # store | pick | cancel
    method: str
    zoneId: str | None = None
    zoneName: str | None = None
    rackId: str | None = None
    rackName: str | None = None
    workerId: str | None = None
    workerName: str | None = None
    timestamp: dt.datetime
    summary: str


class BoxSummary(BaseModel):
    boxId: str
    processStage: str | None = None
    updatedAt: dt.datetime | None = None


# ---------- Dashboard ----------

class RecentPickOut(BaseModel):
    boxId: str
    time: str
    zone: str
    worker: str
    eventType: str


class AlertOut(BaseModel):
    level: str  # info | warning | critical
    title: str
    message: str
    time: str


class DashboardStatsOut(BaseModel):
    itemsStored: int
    itemsProcessing: int
    pendingJobs: int = 0
    capacityPct: int
    activeWorkers: int
    devicesOnline: int
    devicesOffline: int
    recentPicks: list[RecentPickOut]
    alerts: list[AlertOut]
    mode: str


# ---------- Chat ----------

class ChatIn(BaseModel):
    message: str
    sessionId: str | None = None


class ChatAction(BaseModel):
    type: str  # "locate_box"
    boxId: str


class ChatOut(BaseModel):
    reply: str
    action: ChatAction | None = None
    usedTools: list[str] = []
    modelReachable: bool = True


# ---------- System / mode ----------

class ModeOut(BaseModel):
    mode: str
    mqttConnected: bool
    ollamaReachable: bool


class ModeIn(BaseModel):
    mode: str


class WorkerOut(BaseModel):
    id: str
    name: str
    colorHex: str
    active: bool

    class Config:
        from_attributes = True


class SystemConfigOut(BaseModel):
    mqttHost: str
    mqttPort: int
    mqttTopicPrefix: str
    mqttEnabled: bool
    heartbeatTimeoutSec: int
    ollamaHost: str
    ollamaModel: str
