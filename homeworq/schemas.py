from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field, field_validator

from .tasks import Task, get_registered_tasks

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class TimeUnit(str, Enum):
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Settings(BaseModel):
    api_on: bool = Field(
        False,
        description="Enable/disable web service",
    )
    api_auth: bool = Field(
        False,
        description="Enable/disable authentication",
    )
    api_host: str = Field(
        "localhost",
        description="Host address for API server",
    )
    api_port: int = Field(
        8000,
        description="Port for API server",
    )
    debug: bool = Field(False, description="Enable debug mode")
    log_path: Optional[str] = Field(
        None,
        description="Path to log file (default: log to stdout)",
    )
    db_uri: str = Field(
        "sqlite://homeworq.db",
        description="URI for DB connection (may include auth credentials)",
    )


class JobSchedule(BaseModel):
    interval: int = Field(gt=0)
    unit: TimeUnit
    at: Optional[str] = None

    @field_validator("at")
    @classmethod
    def validate_at_time(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                hour, minute = map(int, v.split(":"))
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    raise ValueError("Invalid hour/minute values")
                return f"{hour:02d}:{minute:02d}"
            except ValueError as e:
                s = "'at' must be in HH:MM format (00:00-23:59)"
                raise ValueError(s) from e
        return v


class JobOptions(BaseModel):
    timeout: Optional[int] = Field(None, ge=1)
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class JobBase(BaseModel):
    params: Dict[str, Any]
    options: JobOptions = Field(default_factory=JobOptions)
    schedule: Union[JobSchedule, str]


class JobCreate(JobBase):
    task: str

    @field_validator("task")
    @classmethod
    def validate_task(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("Argument 'task' must be defined.")
        if v in get_registered_tasks():
            return v
        else:
            raise KeyError(f"Task '{v} is not registered.")


class JobUpdate(JobBase):
    params: Optional[Dict[str, Any]] = None
    options: Optional[JobOptions] = None
    schedule: Optional[Union[JobSchedule, str]] = None


class Job(JobBase):
    id: str
    name: str
    task: Task
    created_at: datetime
    updated_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None


class LogBase(BaseModel):
    job_id: str
    status: Status
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries: int = 0


class LogCreate(LogBase):
    pass


class Log(LogBase):
    id: int
    created_at: datetime
    job: Job
