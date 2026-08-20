from pydantic import BaseModel


class DashboardSummary(BaseModel):
    leads: int
    projects: int
    available_units: int
    bookings: int
