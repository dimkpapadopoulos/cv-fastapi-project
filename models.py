from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, UTC
import uuid

class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    status: str = Field(default="PENDING")
    task_type: str
    result: Optional[str] = None
    created_at: datetime = Field(default=datetime.now(UTC))