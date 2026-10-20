# UST Smart Warehouse — Rack Management System (v3)

This is a rebuild of your original `warehouse-system` app: same dashboard,
same zones/devices, same Store/Pick workflow — but the backend is now a
proper FastAPI + SQLAlchemy service instead of an Express/Redis prototype,
architected the way `smart-warehouse-main` was.

```
.
├── backend/     FastAPI + SQLAlchemy + MQTT, port 8000
├── frontend/    React + Vite dashboard, port 5173 (same look as before)
├── mosquitto/   Broker config for docker-compose
└── docker-compose.yml
```

## What changed vs. your original app

| Before (`warehouse-system`) | Now |
|---|---|
| Redis for everything (queues, box state, hardware map) | SQLite (or Postgres) via SQLAlchemy — real tables, real relationships, queryable history |
| One 784-line `app.js` with all logic inline | Routers split by domain: `boxes`, `devices`, `layout`, `dashboard`, `chat`, `system` |
| Public HiveMQ broker, no reconnect handling | Own Mosquitto broker (docker-compose), auto-reconnect + offline watchdog for device health |
| `worker.js` polling a Redis list, 5s hardcoded delay | Persisted `Job` model, same 5s confirm delay, but survives a restart and is queryable |
| No way to know if something failed silently | Structured `job_failed` events with a reason, shown in the event stream |
| Hardcoded MAC→rack map in code | Proper `Gateway` / `ZoneModule` data model — assign/unassign from the UI, no redeploy needed |
| No persistence of zone names/config | `zone_group`, custom name, LED color, module type all persisted and editable from the Properties panel |
| No API docs | Interactive Swagger UI at `http://localhost:8000/docs` |
| No demo mode without hardware | `MODE=mock` simulates gateway heartbeats so the dashboard looks alive with zero physical devices attached |
| No local AI | Optional `/api/chat` endpoint (Ollama) that answers questions using live DB data — off by default, degrades gracefully if not running |

The dashboard itself — header stats, Inbound/Outbound panels, drag-and-drop
grid map, Zone Properties panel, Live Operation Event Stream — looks and
behaves the same as your screenshot. It's now just backed by something you
can actually build on.

## Quick start (Docker Compose — easiest)

```bash
docker compose up --build
```

This starts Mosquitto, the backend, and the frontend. Open
**http://localhost:5173** — you'll see the same dashboard, seeded with
your existing zones (`zone-0`..`zone-5`) and devices.

Optional AI chat: `docker exec -it ust-warehouse-ollama ollama pull qwen3:1.7b`

## Running locally without Docker

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```
Works with zero external services — SQLite by default, and if no MQTT
broker is reachable it just logs a warning and keeps the REST API fully
functional (LED commands are logged but not delivered).

For real LED control: `docker run -p 1883:1883 eclipse-mosquitto:2` (or
install Mosquitto locally).

**No admin rights on your machine?** (e.g. the Mosquitto installer prompts
for admin approval and you can't get it) — use `mosquitto-noadmin/` instead.
It's a tiny pure-JS MQTT broker (via the `aedes` npm package) that runs as
a normal user-level Node process, same as running the frontend:
```bash
cd mosquitto-noadmin
npm install
npm start
```
It listens on `localhost:1883` exactly like Mosquitto would, with the same
kind of verbose connect/publish logging — the backend can't tell the
difference. Leave that window open alongside backend + frontend.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**. Vite proxies `/api` and `/ws` to
`http://localhost:8000` automatically.

## How Store/Pickup works now

Same as before, just backed by a real record instead of a Redis key:

1. You type a Box ID + pick a zone and hit **Store** (or type a Box ID and
   hit **Pickup**).
2. Backend validates it (zone exists, capacity not exceeded, box not
   already staged), creates a `Job` row, turns the zone's LED on over MQTT,
   and broadcasts a `job_queued` event → shows up as `INBOUND QUEUED` /
   `OUTBOUND QUEUED` in the event stream.
3. ~5 seconds later (simulating the pick/place motion — same delay your
   `worker.js` used), the backend commits the box's new location, turns the
   LED off, and broadcasts `job_done` → `PROCESS DONE` in the event stream.

This flow lives in `backend/app/services.py` (`request_store` /
`request_pick`) if you want to change the delay or add a real physical
confirm button later — there's already a `Gateway`/`ZoneModule`
architecture and MQTT `button_press` handler in `mqtt_client.py` ready for
that (adapted from the reference project's RS485 hardware model, currently
unused since your zones don't have physical buttons wired back yet).

## Assigning devices to zones

## The Digital Twin panel is now tabbed

The center "Real-Time Digital Twin Grid Map" panel now has 4 tabs, ported from
`smart-warehouse-main`'s top-level nav into this one panel:

- **Dashboard** — items stored/processing, zone capacity, device health,
  recent operations, system alerts, and the AI assistant chat (talks to
  `/api/chat`; needs a local Ollama server, see below).
- **Live** — the operational view: active operative card, box search &
  locate, task queue, and the grid map in "operate" mode (click to select,
  drag a device from the left sidebar to assign it — no move/resize).
- **Mapping** — rack list, **+ Add Rack**, and **Edit Layout** to unlock free
  drag-to-move / drag-to-resize on the grid (same pointer-based canvas as
  `smart-warehouse-main`'s `DigitalTwinCanvas`, with overlap prevention and
  a double-click box-list modal).
- **Settings** — Mock/Live mode toggle, Device Management (add/remove
  Gateways and Zone Modules, ping, identify/blink), and read-only MQTT / AI
  Assistant configuration pulled from the backend's `.env`.

All 4 tabs are backed by endpoints that already existed in the backend
(`/api/dashboard/stats`, `/api/chat`, `/api/gateways`, `/api/zone-modules`,
`/api/mode`, `/api/system/config`) — nothing new to configure.


Drag a device card from the **Unassigned Devices** panel onto a zone tile
in the grid map, or click a zone then edit it from the **Zone Properties**
panel. Both call `POST /api/zones/{zoneId}/assign` under the hood.

## Configuration

Everything is environment variables — see `backend/.env.example`. Key ones:

| Variable | Purpose |
|---|---|
| `MODE` | `mock` (simulated heartbeats, no hardware needed) or `live` |
| `DATABASE_URL` | SQLite by default; set a `postgresql+psycopg2://...` URL for production |
| `MQTT_HOST` / `MQTT_PORT` / `MQTT_TOPIC_PREFIX` | Your broker (defaults to the bundled Mosquitto, not the public HiveMQ broker your old app used) |
| `OLLAMA_HOST` / `OLLAMA_MODEL` | Optional local AI assistant |

## API surface

- `GET/POST /api/layout` — racks/zones/gateways/zone modules
- `POST /api/zones/{zoneId}/assign` / `/unassign` — drag-and-drop device mapping
- `POST /api/boxes/inbound` / `/outbound` — what the dashboard's Store/Pickup buttons call
- `GET /api/dashboard/stats` — header KPIs (boxes stored, pending, device health)
- `PATCH /api/zone-modules/{id}` — update a device's hardware type
- `GET/POST /api/mode` — Mock/Live toggle
- `GET /api/health` — overall status
- `WS /ws/events` — live push (job queued/done, heartbeats); dashboard falls back to polling if this can't connect
- `POST /api/chat` — optional AI assistant

Full interactive docs at `http://localhost:8000/docs` once running.

## A note on the public broker

Your original app connected to `broker.hivemq.com` — a public, shared
broker anyone can read/write. That's fine for a demo, but not something to
run production hardware on (no auth, no privacy, no reliability
guarantee). This build defaults to your own Mosquitto instance instead. If
you need to keep using a public broker for now, just set `MQTT_HOST` /
`MQTT_PORT` back in `backend/.env`.
