import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import events, migrate, models, runtime_state, seed
from .config import settings
from .database import Base, engine
from .mock_engine import mock_engine
from .mqtt_client import mqtt_service
from .routers import boxes, chat, dashboard, devices, layout, system

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smart_warehouse")

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(layout.router)
app.include_router(devices.router)
app.include_router(boxes.router)
app.include_router(dashboard.router)
app.include_router(chat.router)
app.include_router(system.router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    migrate.run_auto_migrate()
    seed.run()
    runtime_state.init_from_db()
    events.set_main_loop(asyncio.get_event_loop())
    mqtt_service.start()
    mock_engine.start()
    logger.info(
        "Smart Warehouse backend up. mode=%s db=%s mqtt_enabled=%s ollama_model=%s",
        runtime_state.get_mode(),
        settings.DATABASE_URL,
        settings.MQTT_ENABLED,
        settings.OLLAMA_MODEL,
    )


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "running", "docs": "/docs"}


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    """Live push channel for heartbeats / store-pick events / mode changes.
    The frontend falls back to polling automatically if this isn't reachable."""
    await websocket.accept()
    await events.register(websocket)
    try:
        while True:
            # We don't expect inbound messages, just keep the connection open.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await events.unregister(websocket)
