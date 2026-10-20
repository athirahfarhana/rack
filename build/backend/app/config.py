"""
Central configuration for the Smart Warehouse backend.

Everything is controlled via environment variables so the same code runs in:
  - Package A (Software Only / QR):  MQTT_ENABLED can stay on (heartbeats still
    flow from gateways), but there are no LED/button gateways to speak of.
  - Package B/C (Smart PTL / Turnkey): real gateways publish heartbeats + button
    events over MQTT and the backend commands LEDs over MQTT.

MODE toggles between "mock" (built-in simulator plays the role of the gateways
and workers so the app is fully demoable with zero hardware) and "live"
(only real MQTT traffic / real API calls drive the data).
"""
import os
from enum import Enum
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class AppMode(str, Enum):
    MOCK = "mock"
    LIVE = "live"


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # --- General ---
    APP_NAME = "Smart Warehouse Rack Management System"
    MODE: str = os.getenv("MODE", AppMode.MOCK.value).lower()  # "mock" | "live"
    ENV: str = os.getenv("ENV", "development")

    # --- Database ---
    # Defaults to a local SQLite file so the app runs with zero external
    # services. Point DATABASE_URL at Postgres for a real deployment, e.g.:
    #   postgresql+psycopg2://warehouse:warehouse@localhost:5432/warehouse
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smart_warehouse.db")

    # --- MQTT ---
    MQTT_ENABLED: bool = _bool("MQTT_ENABLED", True)
    MQTT_HOST: str = os.getenv("MQTT_HOST", "localhost")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USERNAME: str | None = os.getenv("MQTT_USERNAME") or None
    MQTT_PASSWORD: str | None = os.getenv("MQTT_PASSWORD") or None
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "smart-warehouse-backend")

    # Topic layout: warehouse/racks/{gw_id}/{tx|rx}/{leaf}
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "warehouse/racks")

    # --- Device health / heartbeat ---
    # Real gateways heartbeat every ~60s per spec; flag offline after 3 missed.
    HEARTBEAT_EXPECTED_INTERVAL_SEC: int = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "60"))
    HEARTBEAT_OFFLINE_TIMEOUT_SEC: int = int(os.getenv("HEARTBEAT_TIMEOUT_SEC", "180"))
    HEARTBEAT_WATCHDOG_TICK_SEC: int = int(os.getenv("HEARTBEAT_WATCHDOG_TICK_SEC", "10"))

    # --- Mock simulator ---
    MOCK_TICK_SEC: float = float(os.getenv("MOCK_TICK_SEC", "5"))
    MOCK_FLAKY_DEVICE_CHANCE: float = float(os.getenv("MOCK_FLAKY_DEVICE_CHANCE", "0.03"))

    # --- Ollama (AI chatbot) ---
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
    OLLAMA_TIMEOUT_SEC: float = float(os.getenv("OLLAMA_TIMEOUT_SEC", "30"))
    OLLAMA_MAX_TOOL_ROUNDS: int = int(os.getenv("OLLAMA_MAX_TOOL_ROUNDS", "4"))

    # --- CORS ---
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
        if o.strip()
    ]


settings = Settings()