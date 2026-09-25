"""HTTP shapes: demo checkout input."""
from pydantic import BaseModel


class Checkout(BaseModel):
    item_id: str | None = None
    qty: int = 1
