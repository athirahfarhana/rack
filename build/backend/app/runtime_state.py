"""
Runtime mode toggle (Mock <-> Live), independent of the MODE env var default.

Persisted to the `settings` table so it survives a restart, but cached in a
module-level variable so hot paths (mock simulator tick, dashboard stats)
don't hit the DB just to check the current mode.
"""
import threading

from .config import AppMode, settings
from .database import session_scope
from .models import Setting

_lock = threading.Lock()
_current_mode: str = settings.MODE


def init_from_db() -> None:
    global _current_mode
    with session_scope() as db:
        row = db.query(Setting).filter(Setting.key == "mode").first()
        if row:
            _current_mode = row.value
        else:
            db.add(Setting(key="mode", value=_current_mode))
            db.commit()


def get_mode() -> str:
    return _current_mode


def set_mode(mode: str) -> str:
    global _current_mode
    if mode not in (AppMode.MOCK.value, AppMode.LIVE.value):
        raise ValueError(f"Invalid mode '{mode}'. Must be 'mock' or 'live'.")
    with _lock:
        _current_mode = mode
        with session_scope() as db:
            row = db.query(Setting).filter(Setting.key == "mode").first()
            if row:
                row.value = mode
            else:
                db.add(Setting(key="mode", value=mode))
            db.commit()
    return _current_mode
