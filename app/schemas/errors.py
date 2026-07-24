from pydantic import BaseModel


class ErrorOut(BaseModel):
    """Stable JSON error body for documented API failures."""

    detail: str
