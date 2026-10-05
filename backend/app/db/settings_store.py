from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.db.models import SystemSetting, utcnow


def get_setting(engine: Engine, key: str) -> str | None:
    with Session(engine) as s:
        row = s.get(SystemSetting, key)
        return row.value if row else None


def set_setting(engine: Engine, key: str, value: str | None) -> None:
    with Session(engine) as s:
        row = s.get(SystemSetting, key)
        if value is None:
            if row:
                s.delete(row)
        else:
            row = row or SystemSetting(key=key, value=value)
            row.value = value
            row.updated_at = utcnow()
            s.add(row)
        s.commit()
