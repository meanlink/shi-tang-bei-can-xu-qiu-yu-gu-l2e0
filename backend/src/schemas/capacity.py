from pydantic import BaseModel, Field
class CapacityInput(BaseModel):
    date_from: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    date_to: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    capacity: int = Field(ge=0, le=200000)
