import time
from sqlalchemy import create_engine, text
from app.config import Config

config = Config()

engine = create_engine(
    config.SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280,
)

_DB_STATUS = {"ok": True, "checked_at": 0.0}
_DB_CHECK_TTL_SECONDS = 30  # don’t ping DB on every request

def db_is_ok() -> bool:
    now = time.time()
    if now - _DB_STATUS["checked_at"] < _DB_CHECK_TTL_SECONDS:
        return _DB_STATUS["ok"]

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _DB_STATUS["ok"] = True
    except Exception:
        _DB_STATUS["ok"] = False

    _DB_STATUS["checked_at"] = now
    return _DB_STATUS["ok"]