import json

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.db.settings_store import get_setting, set_setting

PREFIX = "local_price:"
PER = 1_000_000
MAX_PRICE = 1000.0


class LocalPrice(BaseModel):
    input_per_mtok: float = Field(default=0.0, ge=0, le=MAX_PRICE)
    output_per_mtok: float = Field(default=0.0, ge=0, le=MAX_PRICE)

    def per_token(self) -> tuple[float, float]:
        return self.input_per_mtok / PER, self.output_per_mtok / PER


def get_price(engine: Engine, instance_id: str) -> LocalPrice:
    raw = get_setting(engine, PREFIX + instance_id)
    if not raw:
        return LocalPrice()
    try:
        return LocalPrice(**json.loads(raw))
    except (ValueError, TypeError):
        return LocalPrice()


def set_price(engine: Engine, instance_id: str, price: LocalPrice | None) -> None:
    value = None if price is None or price == LocalPrice() else price.model_dump_json()
    set_setting(engine, PREFIX + instance_id, value)
