from pydantic import BaseModel, Field
from .common import Location

class InventoryItem(BaseModel):
    available: float = Field(ge=0)
    capacity: float = Field(ge=0)


class VehicleAvailability(BaseModel):
    total: int = Field(ge=0)
    available: int = Field(ge=0)


class Warehouse(BaseModel):
    warehouse_id: str
    name: str
    location: Location

    inventory: dict[str, InventoryItem]

    vehicles: dict[str, VehicleAvailability]